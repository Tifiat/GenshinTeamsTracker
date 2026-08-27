"""Engine-versioned set-effect semantic manifest.

Only the narrow source shape already proved by the 2p signature parser becomes
typed stat semantics.  Every conditional, triggered, parameterized, indirect,
or otherwise unproved effect remains an opaque engine-bound feature and must be
measured by paired GCSIM set probes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path

from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_two_piece_signatures import (
    GcsimOptimizerTwoPieceProofKind,
    build_gcsim_optimizer_two_piece_effect_descriptors,
)


GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION = 1

_ATTRIBUTE_AXIS = {
    "HP": "hp",
    "ATK": "atk",
    "DEF": "def",
    "HPP": "hp%",
    "ATKP": "atk%",
    "DEFP": "def%",
    "EM": "em",
    "EleMas": "em",
    "ER": "er",
    "CritRate": "cr",
    "CritDamage": "cd",
    "PyroP": "pyro%",
    "HydroP": "hydro%",
    "ElectroP": "electro%",
    "CryoP": "cryo%",
    "AnemoP": "anemo%",
    "GeoP": "geo%",
    "DendroP": "dendro%",
    "PhysicalP": "phys%",
    "Heal": "heal",
}


class GcsimOptimizerSetSemanticStatus(str, Enum):
    SOURCE_PROVED = "source_proved"
    OPAQUE = "opaque"


class GcsimOptimizerSetSemanticError(RuntimeError):
    """Raised when set semantic provenance is incoherent."""


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetSemanticEffect:
    set_key: str
    set_count: int
    status: GcsimOptimizerSetSemanticStatus
    effect_kind: str
    stat_axis: str
    magnitude: str
    source_scope: str
    recipient_scope: str
    trigger: str
    duration: str
    uptime: str
    stacks: str
    modifier_group: str
    stacking_operator: str
    source_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    schema_version: int = GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION:
            raise GcsimOptimizerSetSemanticError(
                "unsupported set semantic schema"
            )
        if self.set_count not in {2, 4}:
            raise GcsimOptimizerSetSemanticError("set_count must be 2 or 4")
        if not isinstance(self.status, GcsimOptimizerSetSemanticStatus):
            raise GcsimOptimizerSetSemanticError("semantic status must be typed")
        for name in (
            "source_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
        ):
            _require_sha256(getattr(self, name), name)
        if self.status is GcsimOptimizerSetSemanticStatus.SOURCE_PROVED:
            if (
                self.effect_kind != "stat"
                or not self.stat_axis
                or not self.magnitude
                or self.source_scope != "wearer"
                or self.recipient_scope != "wearer"
                or self.trigger != "unconditional"
                or self.duration != "infinite"
                or not self.modifier_group
                or self.stacking_operator != "replace_same_group_add_distinct"
            ):
                raise GcsimOptimizerSetSemanticError(
                    "source-proved effect lacks its typed static-stat proof"
                )
        elif any(
            (
                self.stat_axis,
                self.magnitude,
                self.source_scope,
                self.recipient_scope,
                self.trigger,
                self.duration,
                self.uptime,
                self.stacks,
                self.modifier_group,
                self.stacking_operator,
            )
        ):
            raise GcsimOptimizerSetSemanticError(
                "opaque effects cannot invent semantic fields"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "set_key": self.set_key,
            "set_count": self.set_count,
            "status": self.status.value,
            "effect_kind": self.effect_kind,
            "stat_axis": self.stat_axis,
            "magnitude": self.magnitude,
            "source_scope": self.source_scope,
            "recipient_scope": self.recipient_scope,
            "trigger": self.trigger,
            "duration": self.duration,
            "uptime": self.uptime,
            "stacks": self.stacks,
            "modifier_group": self.modifier_group,
            "stacking_operator": self.stacking_operator,
            "source_sha256": self.source_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerSetSemanticManifest:
    effects: tuple[GcsimOptimizerSetSemanticEffect, ...]
    engine_binding_sha256: str
    catalog_fingerprint: str
    identity_sha256: str
    schema_version: int = GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION:
            raise GcsimOptimizerSetSemanticError(
                "unsupported set semantic manifest schema"
            )
        effects = tuple(self.effects)
        if effects != tuple(
            sorted(effects, key=lambda item: (item.set_key, item.set_count))
        ) or len({(item.set_key, item.set_count) for item in effects}) != len(effects):
            raise GcsimOptimizerSetSemanticError(
                "semantic effects must be canonical and unique"
            )
        for name in (
            "engine_binding_sha256",
            "catalog_fingerprint",
            "identity_sha256",
        ):
            _require_sha256(getattr(self, name), name)
        if any(
            item.engine_binding_sha256 != self.engine_binding_sha256
            or item.catalog_fingerprint != self.catalog_fingerprint
            for item in effects
        ):
            raise GcsimOptimizerSetSemanticError(
                "semantic effects differ from their engine/catalog manifest"
            )
        expected = _sha256(
            {
                "schema_version": self.schema_version,
                "engine_binding_sha256": self.engine_binding_sha256,
                "catalog_fingerprint": self.catalog_fingerprint,
                "effects": [item.to_dict() for item in effects],
            }
        )
        if self.identity_sha256 != expected:
            raise GcsimOptimizerSetSemanticError(
                "semantic manifest identity does not match its contents"
            )
        object.__setattr__(self, "effects", effects)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "identity_sha256": self.identity_sha256,
            "effects": [item.to_dict() for item in self.effects],
            "opaque_policy": (
                "paired_set_on_off_and_pair_full_team_gcsim_required"
            ),
        }


def build_gcsim_optimizer_set_semantic_manifest(
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerSetSemanticManifest:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerSetSemanticError("engine_context must be typed")
    if not engine_context.trusted:
        raise GcsimOptimizerSetSemanticError(
            "set semantics require a trusted engine/source binding"
        )
    descriptors = {
        item.set_key: item
        for item in build_gcsim_optimizer_two_piece_effect_descriptors(
            engine_context
        )
    }
    root = Path(engine_context.catalog.source_root)
    effects = []
    for capability in engine_context.catalog.sets:
        source_sha256 = _capability_source_sha256(root, capability.source_files)
        descriptor = descriptors.get(capability.key)
        if capability.two_piece_modeled:
            if (
                descriptor is not None
                and descriptor.proof_kind
                is GcsimOptimizerTwoPieceProofKind.STATIC_STAT
                and len(descriptor.semantic_terms) == 1
                and descriptor.semantic_terms[0][0] in _ATTRIBUTE_AXIS
            ):
                attribute, magnitude = descriptor.semantic_terms[0]
                effects.append(
                    GcsimOptimizerSetSemanticEffect(
                        set_key=capability.key,
                        set_count=2,
                        status=GcsimOptimizerSetSemanticStatus.SOURCE_PROVED,
                        effect_kind="stat",
                        stat_axis=_ATTRIBUTE_AXIS[attribute],
                        magnitude=magnitude,
                        source_scope="wearer",
                        recipient_scope="wearer",
                        trigger="unconditional",
                        duration="infinite",
                        uptime="1",
                        stacks="1",
                        modifier_group=descriptor.modifier_key,
                        stacking_operator=(
                            "replace_same_group_add_distinct"
                        ),
                        source_sha256=source_sha256,
                        engine_binding_sha256=engine_context.binding_sha256,
                        catalog_fingerprint=(
                            engine_context.catalog.source_fingerprint
                        ),
                    )
                )
            else:
                effects.append(
                    _opaque_effect(
                        capability.key,
                        2,
                        source_sha256=source_sha256,
                        engine_context=engine_context,
                    )
                )
        if capability.four_piece_modeled:
            effects.append(
                _opaque_effect(
                    capability.key,
                    4,
                    source_sha256=source_sha256,
                    engine_context=engine_context,
                )
            )
    ordered = tuple(sorted(effects, key=lambda item: (item.set_key, item.set_count)))
    payload = {
        "schema_version": GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION,
        "engine_binding_sha256": engine_context.binding_sha256,
        "catalog_fingerprint": engine_context.catalog.source_fingerprint,
        "effects": [item.to_dict() for item in ordered],
    }
    return GcsimOptimizerSetSemanticManifest(
        effects=ordered,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
        identity_sha256=_sha256(payload),
    )


def _opaque_effect(set_key, set_count, *, source_sha256, engine_context):
    return GcsimOptimizerSetSemanticEffect(
        set_key=set_key,
        set_count=set_count,
        status=GcsimOptimizerSetSemanticStatus.OPAQUE,
        effect_kind="opaque",
        stat_axis="",
        magnitude="",
        source_scope="",
        recipient_scope="",
        trigger="",
        duration="",
        uptime="",
        stacks="",
        modifier_group="",
        stacking_operator="",
        source_sha256=source_sha256,
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
    )


def _capability_source_sha256(root, relative_paths):
    digest = hashlib.sha256()
    for relative in sorted(relative_paths):
        path = root / relative
        if path.suffix != ".go":
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _sha256(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _require_sha256(value, field_name):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GcsimOptimizerSetSemanticError(
            f"{field_name} must be a lowercase SHA-256 digest"
        )


__all__ = [
    "GCSIM_OPTIMIZER_SET_SEMANTICS_SCHEMA_VERSION",
    "GcsimOptimizerSetSemanticEffect",
    "GcsimOptimizerSetSemanticError",
    "GcsimOptimizerSetSemanticManifest",
    "GcsimOptimizerSetSemanticStatus",
    "build_gcsim_optimizer_set_semantic_manifest",
]
