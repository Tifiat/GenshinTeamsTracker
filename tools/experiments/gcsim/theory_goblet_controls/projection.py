"""Compact, conservative projections of schema-6 raw GTT traces."""
from __future__ import annotations

import json
import math
import re
from typing import Any


PROJECTION_SCHEMA = "gtt_theory_goblet_controls_proc_projection_v1"
RAW_SCHEMA_VERSION = 6
ENEMY_TARGET_TYPE = 0
KNOWN_TARGET_TYPES = frozenset({0, 1, 2})
SET_KEYS = (
    "archaicpetra",
    "aubadeofmorningstarandmoon",
    "silkenmoonsserenade",
)
SHA256_FIELDS = (
    "context_sha256",
    "request_sha256",
    "source_config_sha256",
    "compiled_action_sha256",
    "target_sha256",
    "formula_sha256",
    "source_manifest_body_sha256",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _text(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    return value


def _number(value: Any, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if nonnegative and number < 0:
        raise ValueError(f"{label} must be non-negative")
    return number


def _sha256(raw: dict, field: str) -> str:
    value = _text(raw.get(field), field)
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA256 hex")
    return value


def _provider(value: Any, label: str) -> dict:
    provider = _mapping(value, label)
    known = provider.get("known")
    if known is not None and not isinstance(known, bool):
        raise ValueError(f"{label}.known must be boolean when present")
    identity = {
        "kind": _text(provider.get("kind"), f"{label}.kind", allow_empty=True),
        "key": _text(provider.get("key"), f"{label}.key", allow_empty=True),
    }
    if known is not None:
        identity["known"] = known
    for field in ("owner_index", "piece_count"):
        if field in provider and provider[field] is not None:
            identity[field] = _integer(
                provider[field], f"{label}.{field}", minimum=-1 if field == "owner_index" else 0
            )
        else:
            identity[field] = None
    return identity


def _set_key(provider: dict) -> str | None:
    if provider.get("known") is True and provider["kind"] == "set" and provider["key"] in SET_KEYS:
        return provider["key"]
    return None


def _validate_known_set_owner(provider: dict, set_key: str | None, actor_count: int, label: str) -> None:
    if set_key is None:
        return
    owner = provider.get("owner_index")
    if owner is None or owner < 0 or owner >= actor_count:
        raise ValueError(f"{label} has an invalid owner for a known set provider")


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _values(value: Any, label: str) -> dict[str, float]:
    raw_values = _mapping(value, label)
    if any(not isinstance(key, str) for key in raw_values):
        raise ValueError(f"{label} keys must be strings")
    out: dict[str, float] = {}
    for key in sorted(raw_values):
        stat = _text(key, f"{label} key")
        out[stat] = _number(raw_values[key], f"{label}.{stat}")
    return out


def _blank_set_observation() -> dict:
    return {
        "modifier_transition_count": 0,
        "stat_contribution_count": 0,
        "accepted_nonzero_stat_contribution_count": 0,
        "reaction_bonus_contribution_count": 0,
        "nonzero_reaction_bonus_contribution_count": 0,
        "observed_hit_count": 0,
        "observed_enemy_hit_count": 0,
        "observed_recipient_indices": [],
        "modifier_key_counts": {},
    }


def _finite_sum(values: list[float], label: str) -> float:
    try:
        total = math.fsum(values)
    except OverflowError as exc:
        raise ValueError(f"{label} total is not finite") from exc
    if not math.isfinite(total):
        raise ValueError(f"{label} total is not finite")
    return total


def _dps(damage: float, duration_seconds: float, label: str) -> float:
    value = damage / duration_seconds
    if not math.isfinite(value):
        raise ValueError(f"{label} is not finite")
    return value


def project_trace(raw: dict) -> dict:
    """Project one actual schema-6 raw trace without inferring pickup or uptime."""
    raw = _mapping(raw, "trace")
    if _integer(raw.get("schema_version"), "schema_version") != RAW_SCHEMA_VERSION:
        raise ValueError("raw GTT trace schema_version must equal 6")

    seed = _text(raw.get("seed"), "seed")
    if (not seed.isascii() or not seed.isdecimal() or seed.startswith("0") or
            len(seed) > 19):
        raise ValueError("seed must be a canonical positive decimal string")
    seed_value = int(seed)
    if seed_value <= 0 or seed_value >= 1 << 63:
        raise ValueError("seed must be a positive int64")
    duration_frames = _integer(raw.get("duration_frames"), "duration_frames", minimum=1)
    character_keys = _list(raw.get("character_keys"), "character_keys")
    if not character_keys or any(not isinstance(key, str) or not key for key in character_keys):
        raise ValueError("character_keys must contain non-empty strings")
    if len(character_keys) != len(set(character_keys)):
        raise ValueError("character_keys must be unique and preserve actor order")

    hashes = {field: _sha256(raw, field) for field in SHA256_FIELDS}
    engine_version = _text(raw.get("engine_version"), "engine_version")
    actor_damage_values: list[list[float]] = [[] for _ in character_keys]
    actor_hit_count = [0] * len(character_keys)
    enemy_hit_count = 0
    excluded_hit_count = 0
    excluded_damage_values: list[float] = []
    enemy_damage_values: list[float] = []
    transitions_by_set = {key: [] for key in SET_KEYS}
    set_observations = {key: _blank_set_observation() for key in SET_KEYS}
    stat_groups: dict[str, dict] = {}
    hit_set_keys: dict[str, set[str]] = {}
    enemy_hit_set_keys: dict[str, set[str]] = {}
    occurrence_refs: list[tuple[str, str, dict]] = []
    modifier_event_refs: dict[str, tuple[str, str, dict, int, str]] = {}
    seen_hit_ids: set[int] = set()

    hits = _list(raw.get("hits"), "hits")
    if not hits:
        raise ValueError("trace contains no hits")
    for hit_index, raw_hit in enumerate(hits):
        hit = _mapping(raw_hit, f"hits[{hit_index}]")
        target_type = _integer(hit.get("target_type"), f"hits[{hit_index}].target_type", minimum=0)
        if target_type not in KNOWN_TARGET_TYPES:
            raise ValueError(f"hits[{hit_index}].target_type is unknown")
        actor = _integer(hit.get("actor_index"), f"hits[{hit_index}].actor_index", minimum=0)
        if actor >= len(character_keys):
            raise ValueError(f"hits[{hit_index}].actor_index is outside character_keys")
        frame = _integer(hit.get("frame"), f"hits[{hit_index}].frame", minimum=0)
        damage = _number(hit.get("reported_damage"), f"hits[{hit_index}].reported_damage", nonnegative=True)
        hit_id = _integer(hit.get("hit_id"), f"hits[{hit_index}].hit_id", minimum=1)
        if hit_id in seen_hit_ids:
            raise ValueError("trace repeats hit_id")
        seen_hit_ids.add(hit_id)
        if target_type == ENEMY_TARGET_TYPE:
            enemy_hit_count += 1
            enemy_damage_values.append(damage)
            actor_damage_values[actor].append(damage)
            actor_hit_count[actor] += 1
        else:
            excluded_hit_count += 1
            excluded_damage_values.append(damage)

        for contribution_index, raw_contribution in enumerate(
                _list(hit.get("stat_contributions"), f"hits[{hit_index}].stat_contributions")):
            contribution = _mapping(raw_contribution,
                                    f"hits[{hit_index}].stat_contributions[{contribution_index}]")
            provider = _provider(contribution.get("provider"), "stat_contribution.provider")
            set_key = _set_key(provider)
            _validate_known_set_owner(provider, set_key, len(character_keys), "stat_contribution.provider")
            recipient = _integer(contribution.get("recipient_index"), "stat_contribution.recipient_index", minimum=0)
            if recipient >= len(character_keys):
                raise ValueError("stat_contribution.recipient_index is outside character_keys")
            modifier_key = _text(contribution.get("modifier_key"), "stat_contribution.modifier_key", allow_empty=True)
            values = _values(contribution.get("values", {}), "stat_contribution.values")
            accepted = contribution.get("accepted")
            if not isinstance(accepted, bool):
                raise ValueError("stat_contribution.accepted must be boolean")
            modifier_eval_event_id = _text(
                contribution.get("modifier_eval_event_id"),
                "stat_contribution.modifier_eval_event_id",
                allow_empty=True,
            )
            if set_key is None:
                continue
            observation = set_observations[set_key]
            observation["stat_contribution_count"] += 1
            if accepted and any(value != 0 for value in values.values()):
                observation["accepted_nonzero_stat_contribution_count"] += 1
            observation["modifier_key_counts"][modifier_key] = observation["modifier_key_counts"].get(modifier_key, 0) + 1
            key = _json_key([set_key, modifier_key, recipient, provider, accepted, values])
            group = stat_groups.get(key)
            if group is None:
                group = {
                    "set_key": set_key,
                    "modifier_key": modifier_key,
                    "recipient_index": recipient,
                    "recipient_key": character_keys[recipient],
                    "provider": provider,
                    "accepted": accepted,
                    "values": values,
                    "first_frame": frame,
                    "last_frame": frame,
                    "hit_count": 0,
                    "first_hit_id": hit_id,
                    "first_modifier_eval_event_id": modifier_eval_event_id or None,
                    "source_occurrence_ids": [],
                    "modifier_eval_event_ids": [],
                }
                stat_groups[key] = group
            group["first_frame"] = min(group["first_frame"], frame)
            group["last_frame"] = max(group["last_frame"], frame)
            group["hit_count"] += 1
            if modifier_eval_event_id:
                if modifier_eval_event_id not in group["modifier_eval_event_ids"]:
                    group["modifier_eval_event_ids"].append(modifier_eval_event_id)
                ref_key = _json_key(
                    [set_key, modifier_eval_event_id, provider, recipient, modifier_key]
                )
                modifier_event_refs.setdefault(
                    ref_key, (set_key, modifier_eval_event_id, provider, recipient, modifier_key)
                )
            occurrence_id = contribution.get("source_occurrence_id")
            if occurrence_id is not None and occurrence_id != "":
                occurrence_id = _text(occurrence_id, "stat_contribution.source_occurrence_id")
                if occurrence_id not in group["source_occurrence_ids"]:
                    group["source_occurrence_ids"].append(occurrence_id)
                occurrence_refs.append((set_key, occurrence_id, provider))
            hit_set_keys.setdefault(str(hit_id), set()).add(set_key)
            if target_type == ENEMY_TARGET_TYPE:
                enemy_hit_set_keys.setdefault(str(hit_id), set()).add(set_key)

        for contribution_index, raw_contribution in enumerate(
                _list(hit.get("reaction_bonus_contributions"), f"hits[{hit_index}].reaction_bonus_contributions")):
            contribution = _mapping(raw_contribution,
                                    f"hits[{hit_index}].reaction_bonus_contributions[{contribution_index}]")
            provider = _provider(contribution.get("provider"), "reaction_bonus_contribution.provider")
            set_key = _set_key(provider)
            _validate_known_set_owner(provider, set_key, len(character_keys), "reaction_bonus_contribution.provider")
            modifier_key = _text(contribution.get("modifier_key"), "reaction_bonus_contribution.modifier_key", allow_empty=True)
            reaction_bonus_value = _number(
                contribution.get("value"), "reaction_bonus_contribution.value"
            )
            if set_key is None:
                continue
            observation = set_observations[set_key]
            observation["reaction_bonus_contribution_count"] += 1
            if reaction_bonus_value != 0:
                observation["nonzero_reaction_bonus_contribution_count"] += 1
            observation["modifier_key_counts"][modifier_key] = observation["modifier_key_counts"].get(modifier_key, 0) + 1
            hit_set_keys.setdefault(str(hit_id), set()).add(set_key)
            if target_type == ENEMY_TARGET_TYPE:
                enemy_hit_set_keys.setdefault(str(hit_id), set()).add(set_key)
            occurrence_id = contribution.get("source_occurrence_id")
            if occurrence_id is not None and occurrence_id != "":
                occurrence_id = _text(occurrence_id, "reaction_bonus_contribution.source_occurrence_id")
                occurrence_refs.append((set_key, occurrence_id, provider))

    for raw_transition in _list(raw.get("provider_transitions"), "provider_transitions"):
        transition = _mapping(raw_transition, "provider_transition")
        provider = _provider(transition.get("provider"), "provider_transition.provider")
        set_key = _set_key(provider)
        _validate_known_set_owner(provider, set_key, len(character_keys), "provider_transition.provider")
        if set_key is None:
            continue
        frame = _integer(transition.get("frame"), "provider_transition.frame", minimum=-1)
        recipient = _integer(transition.get("recipient_index"), "provider_transition.recipient_index", minimum=-1)
        if recipient >= len(character_keys):
            raise ValueError("provider_transition.recipient_index is outside character_keys")
        modifier_key = _text(transition.get("modifier_key"), "provider_transition.modifier_key", allow_empty=True)
        channel = _text(transition.get("channel"), "provider_transition.channel", allow_empty=True)
        transition_name = _text(transition.get("transition"), "provider_transition.transition", allow_empty=True)
        projected = {
            "frame": frame,
            "channel": channel,
            "recipient_index": recipient,
            "modifier_key": modifier_key,
            "transition": transition_name,
            "provider": provider,
        }
        if "expiry_frame" in transition:
            projected["expiry_frame"] = _integer(transition["expiry_frame"], "provider_transition.expiry_frame", minimum=-1)
        elif "expiry" in transition:
            projected["expiry_frame"] = _integer(transition["expiry"], "provider_transition.expiry", minimum=-1)
        if transition.get("displaced_provider") is not None:
            projected["displaced_provider"] = _provider(transition["displaced_provider"], "provider_transition.displaced_provider")
        transitions_by_set[set_key].append(projected)
        set_observations[set_key]["modifier_transition_count"] += 1
        set_observations[set_key]["modifier_key_counts"][modifier_key] = (
            set_observations[set_key]["modifier_key_counts"].get(modifier_key, 0) + 1
        )
        if recipient >= 0:
            set_observations[set_key]["observed_recipient_indices"].append(recipient)

    for set_key, observation in set_observations.items():
        observation["observed_recipient_indices"] = sorted(set(observation["observed_recipient_indices"]))
        observation["observed_hit_count"] = sum(set_key in keys for keys in hit_set_keys.values())
        observation["observed_enemy_hit_count"] = sum(
            set_key in keys for keys in enemy_hit_set_keys.values()
        )
        observation["modifier_key_counts"] = dict(sorted(observation["modifier_key_counts"].items()))

    occurrence_rows: dict[str, dict] = {}
    for index, raw_occurrence in enumerate(_list(raw.get("source_occurrences"), "source_occurrences")):
        occurrence = _mapping(raw_occurrence, f"source_occurrences[{index}]")
        occurrence_id = _text(occurrence.get("occurrence_id"), "source_occurrence.occurrence_id")
        if occurrence_id in occurrence_rows:
            raise ValueError("duplicate source_occurrence occurrence_id")
        provider = _provider(occurrence.get("provider"), "source_occurrence.provider")
        row = {
            "occurrence_id": occurrence_id,
            "source_id": _text(occurrence.get("source_id"), "source_occurrence.source_id", allow_empty=True),
            "seam": _text(occurrence.get("seam"), "source_occurrence.seam", allow_empty=True),
            "frame": _integer(occurrence.get("frame"), "source_occurrence.frame", minimum=0),
            "provider": provider,
        }
        for field in ("parent_occurrence_id", "terminal_event_id"):
            if occurrence.get(field) is not None:
                row[field] = _text(occurrence[field], f"source_occurrence.{field}", allow_empty=True)
        occurrence_rows[occurrence_id] = row

    wanted_modifier_event_ids = {reference[1] for reference in modifier_event_refs.values()}
    modifier_event_rows: dict[str, dict] = {}
    for index, raw_event in enumerate(_list(raw.get("state_events"), "state_events")):
        event = _mapping(raw_event, f"state_events[{index}]")
        event_id = _text(event.get("event_id"), f"state_events[{index}].event_id")
        if event_id not in wanted_modifier_event_ids:
            continue
        if event_id in modifier_event_rows:
            raise ValueError("duplicate state_event event_id")
        provider = _provider(event.get("provider"), "state_event.provider")
        row = {
            "event_id": event_id,
            "frame": _integer(event.get("frame"), "state_event.frame", minimum=0),
            "kind": _text(event.get("kind"), "state_event.kind"),
            "source_id": _text(event.get("source_id") or "", "state_event.source_id", allow_empty=True),
            "source_occurrence_id": _text(
                event.get("source_occurrence_id") or "",
                "state_event.source_occurrence_id",
                allow_empty=True,
            ),
            "provider": provider,
            "channel": _text(event.get("channel") or "", "state_event.channel", allow_empty=True),
            "modifier_key": _text(event.get("key") or "", "state_event.key", allow_empty=True),
            "owner_index": (
                _integer(event["owner_index"], "state_event.owner_index", minimum=0)
                if event.get("owner_index") is not None else None
            ),
            "output": _values(event.get("output") or {}, "state_event.output"),
        }
        modifier_event_rows[event_id] = row

    occurrence_refs_by_event: dict[tuple[str, str], str] = {}
    occurrence_source_ids: dict[tuple[str, str], set[str]] = {}
    for set_key, event_id, expected_provider, recipient, modifier_key in modifier_event_refs.values():
        event = modifier_event_rows.get(event_id)
        if event is None:
            continue
        if (event["kind"] != "modifier_eval" or event["channel"] != "stat" or
                event["modifier_key"] != modifier_key or event["owner_index"] != recipient or
                event["provider"] != expected_provider):
            raise ValueError(f"modifier evaluation {event_id} does not match its stat contribution")
        occurrence_id = event["source_occurrence_id"]
        if occurrence_id:
            occurrence_refs.append((set_key, occurrence_id, expected_provider))
            occurrence_refs_by_event[(set_key, event_id)] = occurrence_id
            if event["source_id"]:
                occurrence_source_ids.setdefault((set_key, occurrence_id), set()).add(event["source_id"])

    for group in stat_groups.values():
        for event_id in group["modifier_eval_event_ids"]:
            occurrence_id = occurrence_refs_by_event.get((group["set_key"], event_id))
            if occurrence_id and occurrence_id not in group["source_occurrence_ids"]:
                group["source_occurrence_ids"].append(occurrence_id)

    source_proofs: dict[tuple[str, str], dict] = {}
    unmatched_occurrences: set[tuple[str, str]] = set()
    for set_key, occurrence_id, expected_provider in occurrence_refs:
        occurrence = occurrence_rows.get(occurrence_id)
        expected_sources = occurrence_source_ids.get((set_key, occurrence_id), set())
        if (occurrence is None or occurrence["provider"] != expected_provider or
                (expected_sources and occurrence["source_id"] not in expected_sources)):
            unmatched_occurrences.add((set_key, occurrence_id))
            continue
        source_proofs[(set_key, occurrence_id)] = occurrence

    grouped_stats = sorted(
        stat_groups.values(),
        key=lambda row: (row["set_key"], row["recipient_index"], row["modifier_key"],
                         _json_key(row["provider"]), _json_key(row["values"]), row["accepted"]),
    )
    for group in grouped_stats:
        group["modifier_eval_event_ids"].sort()
        group["source_occurrence_ids"].sort()
        group["source_occurrence_proof_ids"] = [
            occurrence_id for occurrence_id in group["source_occurrence_ids"]
            if (group["set_key"], occurrence_id) in source_proofs
        ]

    enemy_total = _finite_sum(enemy_damage_values, "enemy reported damage")
    excluded_total = _finite_sum(excluded_damage_values, "non-enemy reported damage")
    duration_seconds = duration_frames / 60.0
    actor_totals = [
        {
            "actor_index": index,
            "character_key": key,
            "enemy_reported_damage": _finite_sum(actor_damage_values[index],
                                                   f"actor {index} enemy reported damage"),
            "actual_dps": _dps(
                _finite_sum(actor_damage_values[index], f"actor {index} enemy reported damage"),
                duration_seconds,
                f"actor {index} actual DPS",
            ),
            "enemy_hit_count": actor_hit_count[index],
        }
        for index, key in enumerate(character_keys)
    ]
    petra = set_observations["archaicpetra"]
    def modifier_proofs_for_set(set_key: str) -> tuple[list[dict], list[str]]:
        event_ids = sorted({
            event_id
            for group in grouped_stats if group["set_key"] == set_key
            for event_id in group["modifier_eval_event_ids"]
        })
        proofs = []
        unmatched = []
        for event_id in event_ids:
            event = modifier_event_rows.get(event_id)
            if event is None:
                unmatched.append(event_id)
                continue
            occurrence_id = occurrence_refs_by_event.get((set_key, event_id))
            proofs.append({
                **event,
                "source_occurrence_proof_id": (
                    occurrence_id
                    if occurrence_id is not None and (set_key, occurrence_id) in source_proofs
                    else None
                ),
            })
        return proofs, unmatched

    petra_event_proofs, petra_unmatched_modifier_events = modifier_proofs_for_set("archaicpetra")
    return {
        "schema_kind": PROJECTION_SCHEMA,
        "source_schema_version": RAW_SCHEMA_VERSION,
        "identity": {
            "engine_version": engine_version,
            "seed": seed,
            "duration_frames": duration_frames,
            "actor_order": [
                {"actor_index": index, "character_key": key}
                for index, key in enumerate(character_keys)
            ],
            "context_sha256": hashes["context_sha256"],
            "request_sha256": hashes["request_sha256"],
            "source_config_sha256": hashes["source_config_sha256"],
            "compiled_action_sha256": hashes["compiled_action_sha256"],
            "target_sha256": hashes["target_sha256"],
            "formula_sha256": hashes["formula_sha256"],
            "source_manifest_body_sha256": hashes["source_manifest_body_sha256"],
        },
        "damage": {
            "enemy_target_type": ENEMY_TARGET_TYPE,
            "enemy_only": True,
            "enemy_hit_count": enemy_hit_count,
            "enemy_reported_damage": enemy_total,
            "actual_dps": _dps(enemy_total, duration_seconds, "actual DPS"),
            "excluded_non_enemy_hit_count": excluded_hit_count,
            "excluded_non_enemy_reported_damage": excluded_total,
            "actor_totals": actor_totals,
        },
        "petra": {
            "modifier_transitions": transitions_by_set["archaicpetra"],
            "stat_contribution_groups": [row for row in grouped_stats if row["set_key"] == "archaicpetra"],
            "modifier_eval_event_proofs": petra_event_proofs,
            "unmatched_modifier_eval_event_ids": petra_unmatched_modifier_events,
            "source_occurrence_proofs": [
                source_proofs[key] for key in sorted(source_proofs) if key[0] == "archaicpetra"
            ],
            "unmatched_source_occurrence_ids": sorted(
                occurrence_id for set_key, occurrence_id in unmatched_occurrences if set_key == "archaicpetra"
            ),
            "runtime_contribution_count": (
                petra["accepted_nonzero_stat_contribution_count"] +
                petra["nonzero_reaction_bonus_contribution_count"]
            ),
            "runtime_contribution_observed": (
                petra["accepted_nonzero_stat_contribution_count"] +
                petra["nonzero_reaction_bonus_contribution_count"]
            ) > 0,
            "absence_is_not_uptime_or_pickup_proof": True,
            "activation_route": "unknown",
            "pickup": {"status": "unknown", "picker_index": None},
        },
        "set_observations": {
            key: {
                **set_observations[key],
                "stat_contribution_groups": [row for row in grouped_stats if row["set_key"] == key],
                "modifier_eval_event_proofs": modifier_proofs_for_set(key)[0],
                "unmatched_modifier_eval_event_ids": modifier_proofs_for_set(key)[1],
                "source_occurrence_proofs": [
                    source_proofs[source_key]
                    for source_key in sorted(source_proofs) if source_key[0] == key
                ],
                "unmatched_source_occurrence_ids": sorted(
                    occurrence_id for source_key, occurrence_id in unmatched_occurrences if source_key == key
                ),
            }
            for key in SET_KEYS
        },
    }
