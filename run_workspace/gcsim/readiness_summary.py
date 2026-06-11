from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


GROUP_MISSING_CHARACTERS = "missing_characters"
GROUP_MISSING_WEAPONS = "missing_weapons"
GROUP_ARTIFACT_SETS = "artifact_sets"
GROUP_TRAVELER = "traveler"
GROUP_ARTIFACTS = "artifacts"
GROUP_TALENTS_LEVEL_REFINEMENT = "talents_level_refinement"
GROUP_ROTATION_ERRORS = "rotation_errors"

GROUP_TITLES = {
    GROUP_MISSING_CHARACTERS: "Missing characters",
    GROUP_MISSING_WEAPONS: "Missing weapons",
    GROUP_ARTIFACT_SETS: "Artifact set mappings",
    GROUP_TRAVELER: "Traveler",
    GROUP_ARTIFACTS: "Artifacts",
    GROUP_TALENTS_LEVEL_REFINEMENT: "Talents / levels / refinement",
    GROUP_ROTATION_ERRORS: "Rotation / config shell",
}

GROUP_ORDER = (
    GROUP_MISSING_CHARACTERS,
    GROUP_MISSING_WEAPONS,
    GROUP_ARTIFACT_SETS,
    GROUP_TRAVELER,
    GROUP_ARTIFACTS,
    GROUP_TALENTS_LEVEL_REFINEMENT,
    GROUP_ROTATION_ERRORS,
)


@dataclass(frozen=True, slots=True)
class GcsimReadinessSummary:
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return any(self.groups.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "groups": {key: list(value) for key, value in self.groups.items()},
            "text": format_gcsim_readiness_summary(self),
        }


def build_gcsim_readiness_summary(payload: Mapping[str, Any]) -> GcsimReadinessSummary:
    grouped: dict[str, list[str]] = {key: [] for key in GROUP_ORDER}

    team = _mapping(payload.get("team"))
    characters = team.get("characters") if isinstance(team.get("characters"), list) else []
    if not characters and isinstance(payload.get("characters"), list):
        characters = payload.get("characters") or []
    for character in characters:
        if not isinstance(character, Mapping):
            continue
        label = _character_label(character)
        for issue in character.get("issues") or ():
            _add_issue(grouped, issue, label=label)

    for issue in _top_level_issues(payload):
        _add_issue(grouped, issue)

    if _text(payload.get("error_category")) == "config_parse_or_rotation_error":
        error = _text(payload.get("error"))
        _add(grouped, GROUP_ROTATION_ERRORS, error or "Rotation shell/config parse failed.")

    clean = {
        key: tuple(values)
        for key, values in grouped.items()
        if values
    }
    return GcsimReadinessSummary(groups=clean)


def format_gcsim_readiness_summary(
    summary: GcsimReadinessSummary | Mapping[str, Any],
) -> str:
    if isinstance(summary, GcsimReadinessSummary):
        groups = summary.groups
    else:
        raw_groups = summary.get("groups") if isinstance(summary, Mapping) else {}
        groups = {
            str(key): tuple(str(item) for item in value or ())
            for key, value in (raw_groups or {}).items()
        }
    if not any(groups.values()):
        return ""

    lines = ["Readiness summary:"]
    for group in GROUP_ORDER:
        items = groups.get(group) or ()
        if not items:
            continue
        lines.append(f"{GROUP_TITLES[group]}:")
        lines.extend(f"  - {item}" for item in items)
    return "\n".join(lines)


def _top_level_issues(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    issues: list[Mapping[str, Any]] = []
    for issue in payload.get("issues") or ():
        if isinstance(issue, Mapping):
            issues.append(issue)
    full_config = _mapping(payload.get("full_config"))
    for issue in full_config.get("issues") or ():
        if isinstance(issue, Mapping):
            issues.append(issue)
    assembly = _mapping(payload.get("assembly"))
    for issue in assembly.get("issues") or ():
        if isinstance(issue, Mapping):
            issues.append(issue)
    return tuple(issues)


def _add_issue(
    grouped: dict[str, list[str]],
    issue: Any,
    *,
    label: str = "",
) -> None:
    if not isinstance(issue, Mapping):
        return
    status = _text(issue.get("status"))
    field = _text(issue.get("field"))
    message = _text(issue.get("message"))
    issue_label = label or _text(issue.get("display_name")) or _text(issue.get("project_id"))
    text = _issue_text(status=status, field=field, message=message, label=issue_label)
    group = _group_for_issue(status=status, field=field)
    if group:
        _add(grouped, group, text)


def _group_for_issue(*, status: str, field: str) -> str:
    probe = f"{status} {field}".casefold()
    if "traveler" in probe or "unsupported_traveler" in probe:
        return GROUP_TRAVELER
    if "shell" in probe or "rotation" in probe:
        return GROUP_ROTATION_ERRORS
    if "selected_team_empty" in probe or "selected_team.slots" in probe:
        return GROUP_MISSING_CHARACTERS
    if "weapon" in probe:
        if "refinement" in probe or "level" in probe:
            return GROUP_TALENTS_LEVEL_REFINEMENT
        return GROUP_MISSING_WEAPONS
    if "character" in probe and (
        "missing" in probe
        or "selected_character_id_missing" in probe
        or "account_character_missing" in probe
    ):
        return GROUP_MISSING_CHARACTERS
    if "artifact_set" in probe or "set_uid" in probe:
        return GROUP_ARTIFACT_SETS
    if "artifact" in probe:
        return GROUP_ARTIFACTS
    if (
        "talent" in probe
        or "level" in probe
        or "constellation" in probe
        or "refinement" in probe
    ):
        return GROUP_TALENTS_LEVEL_REFINEMENT
    return ""


def _issue_text(*, status: str, field: str, message: str, label: str) -> str:
    parts = []
    if label:
        parts.append(label)
    details = message or status or field
    if label and details:
        parts.append(details)
    elif details:
        parts.append(details)
    if field and field not in details:
        parts.append(f"field={field}")
    return ": ".join(parts)


def _character_label(character: Mapping[str, Any]) -> str:
    account = _mapping(character.get("account_character"))
    payload = _mapping(character.get("payload_character"))
    slot_index = character.get("slot_index")
    label = (
        _text(account.get("catalog_english_name"))
        or _text(account.get("localized_name"))
        or _text(payload.get("display_name"))
        or f"slot {slot_index}"
    )
    return label


def _add(grouped: dict[str, list[str]], group: str, value: str) -> None:
    text = _text(value)
    if not text or text in grouped[group]:
        return
    grouped[group].append(text)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
