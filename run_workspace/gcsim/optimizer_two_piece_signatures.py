"""Engine-derived 2p semantic signatures and theoretical pair domains.

Only a deliberately narrow, self-contained static-stat source shape is grouped
across concrete sets. Everything conditional, parameterized, indirect, or
otherwise unproved receives a unique engine-bound signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
import hashlib
import json
from itertools import combinations
from pathlib import Path
import re

from .artifact_set_catalog import GcsimArtifactSetCapability
from .optimizer_engine_context import GcsimOptimizerEngineContext
from .optimizer_product_contracts import (
    GcsimOptimizerSetReference,
    GcsimTwoPlusTwoTargetPackage,
)


GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION = 1

_TWO_PIECE_IF_RE = re.compile(r"\bif\s+count\s*>=\s*2\s*\{")
_STATIC_STAT_BLOCK_RE = re.compile(
    r'^m:=make\(\[\]float64,attributes\.EndStatType\)'
    r'm\[attributes\.(?P<assigned>[A-Za-z0-9_]+)\]='
    r'(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+))'
    r'(?P<receiver>[A-Za-z_][A-Za-z0-9_.]*)\.AddStatMod'
    r'\(character\.StatMod\{'
    r'Base:modifier\.NewBase\("(?P<label>[^"]+)",-1\),'
    r'AffectedStat:attributes\.(?P<affected>[A-Za-z0-9_]+),'
    r'Amount:func\(\)\[\]float64\{returnm\},'
    r'\}\)$'
)
_NEW_SET_FUNCTION_RE = re.compile(
    r"\bfunc\s+NewSet\s*\((?P<parameters>[^)]*)\)[^{]*\{"
)
_CHARACTER_PARAMETER_RE = re.compile(
    r"\b(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+\*character\.CharWrapper\b"
)
_COUNT_PARAMETER_RE = re.compile(r"\bcount\s+int\b")
_INACTIVE_COUNT_BLOCK_RE = re.compile(
    r"\bif\s+count\s*>=\s*(?P<count>[3-9]|[1-9][0-9]+)\s*\{"
)
_COUNT_TWO_RETURN_GUARD_RE = re.compile(
    r"\bif\s+count\s*<\s*(?P<count>[3-9]|[1-9][0-9]+)\s*\{"
)
_OUTSIDE_MUTATION_RE = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.]*\."
    r"(?:Add[A-Za-z0-9_]*|Delete[A-Za-z0-9_]*|Subscribe|"
    r"Queue[A-Za-z0-9_]*|Set[A-Z][A-Za-z0-9_]*)\s*\("
)

_MODIFIER_KEY_RELATION_DISTINCT = "distinct_static_keys"
_MODIFIER_KEY_RELATION_SAME = "same_static_key"
_MODIFIER_KEY_RELATION_OPAQUE = "opaque_unique_source"
_MODIFIER_KEY_RELATIONS = frozenset(
    {
        _MODIFIER_KEY_RELATION_DISTINCT,
        _MODIFIER_KEY_RELATION_SAME,
        _MODIFIER_KEY_RELATION_OPAQUE,
    }
)


@dataclass(frozen=True, slots=True)
class _ProvedStaticStatEffect:
    semantic_terms: tuple[tuple[str, str], ...]
    modifier_key: str


class GcsimOptimizerTwoPieceSignatureError(RuntimeError):
    """Raised when a frozen engine/catalog pair domain is incoherent."""


class GcsimOptimizerTwoPieceProofKind(str, Enum):
    STATIC_STAT = "static_stat"
    UNIQUE_SOURCE = "unique_source"


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTwoPieceEffectDescriptor:
    set_key: str
    effect_signature_sha256: str
    proof_kind: GcsimOptimizerTwoPieceProofKind
    semantic_terms: tuple[tuple[str, str], ...]
    source_sha256: str
    engine_binding_sha256: str
    catalog_fingerprint: str
    parameter_keys: tuple[str, ...] = ()
    modifier_key: str = ""
    schema_version: int = GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION:
            raise GcsimOptimizerTwoPieceSignatureError(
                "unsupported 2p signature schema"
            )
        if not isinstance(self.proof_kind, GcsimOptimizerTwoPieceProofKind):
            raise GcsimOptimizerTwoPieceSignatureError(
                "proof_kind must be typed"
            )
        if not isinstance(self.set_key, str) or re.fullmatch(
            r"[a-z0-9]+",
            self.set_key,
        ) is None:
            raise GcsimOptimizerTwoPieceSignatureError(
                "set_key must be a canonical GCSIM set key"
            )
        for field_name in (
            "effect_signature_sha256",
            "source_sha256",
            "engine_binding_sha256",
            "catalog_fingerprint",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        try:
            semantic_terms = tuple(tuple(item) for item in self.semantic_terms)
            parameter_keys = tuple(self.parameter_keys)
        except TypeError as exc:
            raise GcsimOptimizerTwoPieceSignatureError(
                "semantic_terms and parameter_keys must be iterable"
            ) from exc
        object.__setattr__(self, "semantic_terms", semantic_terms)
        object.__setattr__(self, "parameter_keys", parameter_keys)
        if any(
            len(item) != 2
            or not isinstance(item[0], str)
            or re.fullmatch(r"[A-Za-z0-9_]+", item[0]) is None
            or not isinstance(item[1], str)
            or _canonical_decimal(item[1]) != item[1]
            for item in semantic_terms
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "semantic_terms must contain canonical stat/value pairs"
            )
        if semantic_terms != tuple(sorted(semantic_terms)) or len(
            set(semantic_terms)
        ) != len(semantic_terms):
            raise GcsimOptimizerTwoPieceSignatureError(
                "semantic_terms must be sorted and unique"
            )
        if parameter_keys != tuple(sorted(parameter_keys)) or len(
            set(parameter_keys)
        ) != len(parameter_keys) or any(
            not isinstance(item, str)
            or re.fullmatch(r"[a-z0-9_]+", item) is None
            for item in parameter_keys
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "parameter_keys must be sorted unique canonical keys"
            )
        if (
            self.proof_kind is GcsimOptimizerTwoPieceProofKind.STATIC_STAT
            and not semantic_terms
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "static-stat proof requires semantic terms"
            )
        if (
            self.proof_kind is GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE
            and semantic_terms
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "unique-source proof cannot claim semantic terms"
            )
        if self.proof_kind is GcsimOptimizerTwoPieceProofKind.STATIC_STAT:
            if (
                not isinstance(self.modifier_key, str)
                or not self.modifier_key
                or self.modifier_key != self.modifier_key.strip()
                or any(ord(character) < 32 for character in self.modifier_key)
            ):
                raise GcsimOptimizerTwoPieceSignatureError(
                    "static-stat proof requires a literal modifier key"
                )
        elif self.modifier_key:
            raise GcsimOptimizerTwoPieceSignatureError(
                "unique-source proof cannot claim a modifier key"
            )
        expected_signature = _sha256(
            _effect_signature_payload(
                set_key=self.set_key,
                proof_kind=self.proof_kind,
                semantic_terms=semantic_terms,
                source_sha256=self.source_sha256,
                engine_binding_sha256=self.engine_binding_sha256,
                catalog_fingerprint=self.catalog_fingerprint,
            )
        )
        if self.effect_signature_sha256 != expected_signature:
            raise GcsimOptimizerTwoPieceSignatureError(
                "effect signature does not match its typed proof"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "set_key": self.set_key,
            "effect_signature_sha256": self.effect_signature_sha256,
            "proof_kind": self.proof_kind.value,
            "semantic_terms": [list(item) for item in self.semantic_terms],
            "source_sha256": self.source_sha256,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "parameter_keys": list(self.parameter_keys),
            "modifier_key": self.modifier_key,
            "receiver_binding": (
                "registered_constructor_character"
                if self.proof_kind
                is GcsimOptimizerTwoPieceProofKind.STATIC_STAT
                else ""
            ),
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalPairGroup:
    pair_signature_sha256: str
    representative: GcsimTwoPlusTwoTargetPackage
    concrete_aliases: tuple[GcsimTwoPlusTwoTargetPackage, ...]
    effect_signature_pair: tuple[str, str]
    modifier_key_relation: str
    canonical_slot_shape: tuple[int, int] = (3, 2)
    schema_version: int = GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION:
            raise GcsimOptimizerTwoPieceSignatureError(
                "unsupported theoretical pair-group schema"
            )
        _require_sha256(self.pair_signature_sha256, "pair_signature_sha256")
        if not isinstance(self.representative, GcsimTwoPlusTwoTargetPackage):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair representative must be typed"
            )
        try:
            aliases = tuple(self.concrete_aliases)
        except TypeError as exc:
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair aliases must be iterable"
            ) from exc
        object.__setattr__(self, "concrete_aliases", aliases)
        if any(
            not isinstance(item, GcsimTwoPlusTwoTargetPackage)
            for item in aliases
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair aliases must be typed 2p+2p packages"
            )
        if not aliases or self.representative != aliases[0]:
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair representative must be the first concrete alias"
            )
        if len(set(item.identity_sha256 for item in aliases)) != len(aliases):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair aliases must be physically unique"
            )
        if aliases != tuple(sorted(aliases, key=_package_sort_key)):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair aliases must use canonical order"
            )
        try:
            effect_pair = tuple(self.effect_signature_pair)
        except TypeError as exc:
            raise GcsimOptimizerTwoPieceSignatureError(
                "effect_signature_pair must be iterable"
            ) from exc
        object.__setattr__(self, "effect_signature_pair", effect_pair)
        if (
            len(effect_pair) != 2
            or any(not _is_sha256(item) for item in effect_pair)
            or effect_pair != tuple(sorted(effect_pair))
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "effect_signature_pair must contain two sorted SHA-256 digests"
            )
        if self.modifier_key_relation not in _MODIFIER_KEY_RELATIONS:
            raise GcsimOptimizerTwoPieceSignatureError(
                "modifier_key_relation is unsupported"
            )
        try:
            slot_shape = tuple(self.canonical_slot_shape)
        except TypeError as exc:
            raise GcsimOptimizerTwoPieceSignatureError(
                "canonical_slot_shape must be iterable"
            ) from exc
        object.__setattr__(self, "canonical_slot_shape", slot_shape)
        if slot_shape != (3, 2):
            raise GcsimOptimizerTwoPieceSignatureError(
                "theoretical pair slot shape must use canonical 3+2"
            )
        bindings = {
            set_ref.engine_binding_sha256
            for item in aliases
            for set_ref in (item.set_a, item.set_b)
        }
        catalogs = {
            set_ref.catalog_fingerprint
            for item in aliases
            for set_ref in (item.set_a, item.set_b)
        }
        if len(bindings) != 1 or len(catalogs) != 1:
            raise GcsimOptimizerTwoPieceSignatureError(
                "one pair group must share one engine/catalog binding"
            )
        opaque_set_pair = (
            _package_set_key_pair(self.representative)
            if self.modifier_key_relation != _MODIFIER_KEY_RELATION_DISTINCT
            else ()
        )
        expected_signature = _pair_signature_sha256(
            engine_binding_sha256=next(iter(bindings)),
            catalog_fingerprint=next(iter(catalogs)),
            effect_signature_pair=effect_pair,
            modifier_key_relation=self.modifier_key_relation,
            opaque_set_pair=opaque_set_pair,
        )
        if self.pair_signature_sha256 != expected_signature:
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair signature does not match its typed proof"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "pair_signature_sha256": self.pair_signature_sha256,
            "effect_signature_pair": list(self.effect_signature_pair),
            "modifier_key_relation": self.modifier_key_relation,
            "canonical_slot_shape": list(self.canonical_slot_shape),
            "representative": self.representative.to_dict(),
            "concrete_aliases": [
                item.to_dict() for item in self.concrete_aliases
            ],
        }


@dataclass(frozen=True, slots=True)
class GcsimOptimizerTheoreticalPairDomain:
    descriptors: tuple[GcsimOptimizerTwoPieceEffectDescriptor, ...]
    groups: tuple[GcsimOptimizerTheoreticalPairGroup, ...]
    concrete_pair_count: int
    engine_binding_sha256: str
    catalog_fingerprint: str
    schema_version: int = GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION:
            raise GcsimOptimizerTwoPieceSignatureError(
                "unsupported theoretical pair-domain schema"
            )
        _require_sha256(self.engine_binding_sha256, "engine_binding_sha256")
        _require_sha256(self.catalog_fingerprint, "catalog_fingerprint")
        try:
            descriptors = tuple(self.descriptors)
            groups = tuple(self.groups)
        except TypeError as exc:
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair descriptors and groups must be iterable"
            ) from exc
        object.__setattr__(self, "descriptors", descriptors)
        object.__setattr__(self, "groups", groups)
        if any(
            not isinstance(item, GcsimOptimizerTwoPieceEffectDescriptor)
            for item in descriptors
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair domain descriptors must be typed"
            )
        if any(
            not isinstance(item, GcsimOptimizerTheoreticalPairGroup)
            for item in groups
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair domain groups must be typed"
            )
        if descriptors != tuple(sorted(descriptors, key=lambda item: item.set_key)):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair descriptors must use canonical set-key order"
            )
        if len({item.set_key for item in descriptors}) != len(descriptors):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair descriptors must have unique set keys"
            )
        if any(
            item.engine_binding_sha256 != self.engine_binding_sha256
            or item.catalog_fingerprint != self.catalog_fingerprint
            for item in descriptors
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair descriptors differ from the domain engine/catalog binding"
            )
        if groups != tuple(sorted(groups, key=_group_sort_key)):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair groups must use canonical proof order"
            )
        if len({item.pair_signature_sha256 for item in groups}) != len(groups):
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair groups must have unique signatures"
            )
        if (
            isinstance(self.concrete_pair_count, bool)
            or not isinstance(self.concrete_pair_count, int)
            or self.concrete_pair_count < 0
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "concrete_pair_count must be a non-negative integer"
            )
        if self.concrete_pair_count != sum(
            len(group.concrete_aliases) for group in groups
        ):
            raise GcsimOptimizerTwoPieceSignatureError(
                "concrete pair count differs from alias groups"
            )
        expected_pair_count = len(descriptors) * (len(descriptors) - 1) // 2
        if self.concrete_pair_count != expected_pair_count:
            raise GcsimOptimizerTwoPieceSignatureError(
                "concrete pair count does not cover the descriptor domain"
            )
        descriptor_by_key = {item.set_key: item for item in descriptors}
        actual_pairs: set[tuple[str, str]] = set()
        for group in groups:
            for package in group.concrete_aliases:
                set_key_pair = _package_set_key_pair(package)
                if set_key_pair in actual_pairs:
                    raise GcsimOptimizerTwoPieceSignatureError(
                        "concrete pair appears in more than one proof group"
                    )
                actual_pairs.add(set_key_pair)
                if any(key not in descriptor_by_key for key in set_key_pair):
                    raise GcsimOptimizerTwoPieceSignatureError(
                        "pair alias references a set without a descriptor"
                    )
                for set_ref in (package.set_a, package.set_b):
                    if (
                        set_ref.engine_binding_sha256
                        != self.engine_binding_sha256
                        or set_ref.catalog_fingerprint
                        != self.catalog_fingerprint
                    ):
                        raise GcsimOptimizerTwoPieceSignatureError(
                            "pair alias differs from the domain engine/catalog binding"
                        )
                    descriptor = descriptor_by_key[set_ref.gcsim_set_key]
                    if any(
                        key not in descriptor.parameter_keys
                        for key in set_ref.set_parameters
                    ):
                        raise GcsimOptimizerTwoPieceSignatureError(
                            "pair alias uses an unproved set parameter"
                        )
                expected_effect_pair = tuple(
                    sorted(
                        descriptor_by_key[key].effect_signature_sha256
                        for key in set_key_pair
                    )
                )
                expected_relation = _modifier_key_relation(
                    *(descriptor_by_key[key] for key in set_key_pair)
                )
                if (
                    group.effect_signature_pair != expected_effect_pair
                    or group.modifier_key_relation != expected_relation
                ):
                    raise GcsimOptimizerTwoPieceSignatureError(
                        "pair alias does not match its effect/modifier proof group"
                    )
                if (
                    expected_relation != _MODIFIER_KEY_RELATION_DISTINCT
                    and len(group.concrete_aliases) != 1
                ):
                    raise GcsimOptimizerTwoPieceSignatureError(
                        "opaque or colliding-modifier pairs cannot share an alias group"
                    )
        expected_pairs = {
            tuple(sorted(pair))
            for pair in combinations(descriptor_by_key, 2)
        }
        if actual_pairs != expected_pairs:
            raise GcsimOptimizerTwoPieceSignatureError(
                "pair aliases do not exactly cover every concrete set pair"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_binding_sha256": self.engine_binding_sha256,
            "catalog_fingerprint": self.catalog_fingerprint,
            "concrete_pair_count": self.concrete_pair_count,
            "descriptors": [item.to_dict() for item in self.descriptors],
            "groups": [item.to_dict() for item in self.groups],
        }


def build_gcsim_optimizer_two_piece_effect_descriptors(
    engine_context: GcsimOptimizerEngineContext,
) -> tuple[GcsimOptimizerTwoPieceEffectDescriptor, ...]:
    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerTwoPieceSignatureError(
            "engine_context must be typed"
        )
    if not engine_context.trusted:
        raise GcsimOptimizerTwoPieceSignatureError(
            "engine context must be trusted"
        )
    descriptors = [
        _descriptor(engine_context, capability)
        for capability in engine_context.catalog.sets
        if capability.two_piece_modeled and capability.max_rarity == 5
    ]
    return tuple(sorted(descriptors, key=lambda item: item.set_key))


def build_gcsim_optimizer_guaranteed_two_piece_stat_effects(
    engine_context: GcsimOptimizerEngineContext,
) -> tuple[GcsimOptimizerTwoPieceEffectDescriptor, ...]:
    """Return only source-proved unconditional 2p stat effects.

    Unlike the theoretical pair domain, this account legality helper also
    inspects explicitly eligible four-star sets.  Opaque, conditional,
    parameterized, indirect, or otherwise unproved effects are deliberately
    absent so a pre-simulation hard floor can never assume a conditional buff.
    """

    if not isinstance(engine_context, GcsimOptimizerEngineContext):
        raise GcsimOptimizerTwoPieceSignatureError(
            "engine_context must be typed"
        )
    if not engine_context.trusted:
        raise GcsimOptimizerTwoPieceSignatureError(
            "engine context must be trusted"
        )
    descriptors = (
        _descriptor(engine_context, capability)
        for capability in engine_context.catalog.sets
        if capability.two_piece_modeled
    )
    return tuple(
        sorted(
            (
                descriptor
                for descriptor in descriptors
                if descriptor.proof_kind
                is GcsimOptimizerTwoPieceProofKind.STATIC_STAT
            ),
            key=lambda item: item.set_key,
        )
    )


def build_gcsim_optimizer_theoretical_pair_domain(
    engine_context: GcsimOptimizerEngineContext,
) -> GcsimOptimizerTheoreticalPairDomain:
    descriptors = build_gcsim_optimizer_two_piece_effect_descriptors(
        engine_context
    )
    by_key = {item.set_key: item for item in descriptors}
    groups: dict[tuple[str, ...], list[GcsimTwoPlusTwoTargetPackage]] = {}
    for set_a, set_b in combinations(sorted(by_key), 2):
        package = GcsimTwoPlusTwoTargetPackage(
            GcsimOptimizerSetReference(
                set_uid=set_a,
                gcsim_set_key=set_a,
                engine_binding_sha256=engine_context.binding_sha256,
                catalog_fingerprint=engine_context.catalog.source_fingerprint,
            ),
            GcsimOptimizerSetReference(
                set_uid=set_b,
                gcsim_set_key=set_b,
                engine_binding_sha256=engine_context.binding_sha256,
                catalog_fingerprint=engine_context.catalog.source_fingerprint,
            ),
        )
        signature_pair = tuple(
            sorted(
                (
                    by_key[set_a].effect_signature_sha256,
                    by_key[set_b].effect_signature_sha256,
                )
            )
        )
        relation = _modifier_key_relation(by_key[set_a], by_key[set_b])
        group_key = (
            *signature_pair,
            relation,
            *(
                tuple(sorted((set_a, set_b)))
                if relation != _MODIFIER_KEY_RELATION_DISTINCT
                else ()
            ),
        )
        groups.setdefault(group_key, []).append(package)
    result_groups = []
    for group_key, packages in sorted(groups.items()):
        signature_pair = (group_key[0], group_key[1])
        relation = group_key[2]
        opaque_set_pair = (
            (group_key[3], group_key[4])
            if relation != _MODIFIER_KEY_RELATION_DISTINCT
            else ()
        )
        aliases = tuple(
            sorted(
                packages,
                key=_package_sort_key,
            )
        )
        result_groups.append(
            GcsimOptimizerTheoreticalPairGroup(
                pair_signature_sha256=_pair_signature_sha256(
                    engine_binding_sha256=engine_context.binding_sha256,
                    catalog_fingerprint=(
                        engine_context.catalog.source_fingerprint
                    ),
                    effect_signature_pair=signature_pair,
                    modifier_key_relation=relation,
                    opaque_set_pair=opaque_set_pair,
                ),
                representative=aliases[0],
                concrete_aliases=aliases,
                effect_signature_pair=signature_pair,
                modifier_key_relation=relation,
            )
        )
    result_groups.sort(key=_group_sort_key)
    return GcsimOptimizerTheoreticalPairDomain(
        descriptors=descriptors,
        groups=tuple(result_groups),
        concrete_pair_count=sum(
            len(group.concrete_aliases) for group in result_groups
        ),
        engine_binding_sha256=engine_context.binding_sha256,
        catalog_fingerprint=engine_context.catalog.source_fingerprint,
    )


def _descriptor(
    context: GcsimOptimizerEngineContext,
    capability: GcsimArtifactSetCapability,
) -> GcsimOptimizerTwoPieceEffectDescriptor:
    root = Path(context.catalog.source_root)
    sources = []
    for relative in capability.source_files:
        path = root / relative
        if path.suffix == ".go":
            sources.append(path.read_text(encoding="utf-8", errors="strict"))
    joined = "\n".join(sources)
    source_sha256 = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    static_proof = (
        None
        if capability.parameter_keys
        else _proved_static_stat_effect(joined)
    )
    if static_proof is not None:
        proof_kind = GcsimOptimizerTwoPieceProofKind.STATIC_STAT
        terms = static_proof.semantic_terms
        modifier_key = static_proof.modifier_key
    else:
        proof_kind = GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE
        terms = ()
        modifier_key = ""
    signature_payload = _effect_signature_payload(
        set_key=capability.key,
        proof_kind=proof_kind,
        semantic_terms=terms,
        source_sha256=source_sha256,
        engine_binding_sha256=context.binding_sha256,
        catalog_fingerprint=context.catalog.source_fingerprint,
    )
    return GcsimOptimizerTwoPieceEffectDescriptor(
        set_key=capability.key,
        effect_signature_sha256=_sha256(signature_payload),
        proof_kind=proof_kind,
        semantic_terms=terms,
        source_sha256=source_sha256,
        engine_binding_sha256=context.binding_sha256,
        catalog_fingerprint=context.catalog.source_fingerprint,
        parameter_keys=capability.parameter_keys,
        modifier_key=modifier_key,
    )


def _proved_static_stat_terms(source: str) -> tuple[tuple[str, str], ...]:
    """Compatibility helper retained for focused parser tests."""

    proof = _proved_static_stat_effect(source)
    return () if proof is None else proof.semantic_terms


def _proved_static_stat_effect(source: str) -> _ProvedStaticStatEffect | None:
    clean = _strip_go_comments(source)
    function_matches = tuple(_NEW_SET_FUNCTION_RE.finditer(clean))
    if len(function_matches) != 1:
        return None
    function_match = function_matches[0]
    parameters = function_match.group("parameters")
    character_parameters = tuple(
        item.group("name") for item in _CHARACTER_PARAMETER_RE.finditer(parameters)
    )
    if len(character_parameters) != 1 or _COUNT_PARAMETER_RE.search(
        parameters
    ) is None:
        return None
    function_span = _brace_span(clean, function_match.end() - 1)
    if function_span is None:
        return None
    function_open, function_close = function_span
    function_body = clean[function_open + 1 : function_close]
    matches = tuple(_TWO_PIECE_IF_RE.finditer(function_body))
    if len(matches) != 1:
        return None
    block_span = _brace_span(function_body, matches[0].end() - 1)
    if block_span is None:
        return None
    block_open, block_close = block_span
    block = function_body[block_open + 1 : block_close]
    normalized = re.sub(r"\s+", "", block)
    match = _STATIC_STAT_BLOCK_RE.fullmatch(normalized)
    if (
        match is None
        or match.group("assigned") != match.group("affected")
        or match.group("receiver") != character_parameters[0]
    ):
        return None
    value = _canonical_decimal(match.group("value"))
    if value is None:
        return None
    if _has_count_two_reachable_mutation_outside_block(
        function_body,
        two_piece_if_start=matches[0].start(),
        two_piece_block_close=block_close,
    ):
        return None
    return _ProvedStaticStatEffect(
        semantic_terms=((match.group("assigned"), value),),
        modifier_key=match.group("label"),
    )


def _has_count_two_reachable_mutation_outside_block(
    function_body: str,
    *,
    two_piece_if_start: int,
    two_piece_block_close: int,
) -> bool:
    reachable = (
        function_body[:two_piece_if_start]
        + " " * (two_piece_block_close + 1 - two_piece_if_start)
        + function_body[two_piece_block_close + 1 :]
    )
    while True:
        match = _INACTIVE_COUNT_BLOCK_RE.search(reachable)
        if match is None:
            break
        span = _brace_span(reachable, match.end() - 1)
        if span is None:
            return True
        reachable = (
            reachable[: match.start()]
            + " " * (span[1] + 1 - match.start())
            + reachable[span[1] + 1 :]
        )
    for match in _COUNT_TWO_RETURN_GUARD_RE.finditer(reachable):
        span = _brace_span(reachable, match.end() - 1)
        if span is None:
            return True
        guard_body = reachable[span[0] + 1 : span[1]]
        if re.search(r"\breturn\b", guard_body):
            reachable = reachable[: span[1] + 1]
            break
    return _OUTSIDE_MUTATION_RE.search(reachable) is not None


def _brace_span(source: str, opening_index: int) -> tuple[int, int] | None:
    depth = 0
    in_string = False
    escaped = False
    for index in range(opening_index, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return opening_index, index
    return None


def _brace_body(source: str, opening_index: int) -> str | None:
    span = _brace_span(source, opening_index)
    if span is None:
        return None
    return source[span[0] + 1 : span[1]]


def _canonical_decimal(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    if not parsed.is_finite():
        return None
    return format(parsed.normalize(), "f")


def _effect_signature_payload(
    *,
    set_key: str,
    proof_kind: GcsimOptimizerTwoPieceProofKind,
    semantic_terms: tuple[tuple[str, str], ...],
    source_sha256: str,
    engine_binding_sha256: str,
    catalog_fingerprint: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION,
        "engine_binding_sha256": engine_binding_sha256,
        "catalog_fingerprint": catalog_fingerprint,
        "proof_kind": proof_kind.value,
    }
    if proof_kind is GcsimOptimizerTwoPieceProofKind.STATIC_STAT:
        payload.update(
            {
                "semantic_terms": [list(item) for item in semantic_terms],
                "receiver_proof": "registered_constructor_character",
                "modifier_interaction": "pair_collision_relation_v1",
            }
        )
    else:
        payload.update(
            {
                "set_key": set_key,
                "source_sha256": source_sha256,
            }
        )
    return payload


def _modifier_key_relation(
    left: GcsimOptimizerTwoPieceEffectDescriptor,
    right: GcsimOptimizerTwoPieceEffectDescriptor,
) -> str:
    if (
        left.proof_kind is not GcsimOptimizerTwoPieceProofKind.STATIC_STAT
        or right.proof_kind is not GcsimOptimizerTwoPieceProofKind.STATIC_STAT
    ):
        return _MODIFIER_KEY_RELATION_OPAQUE
    if left.modifier_key == right.modifier_key:
        return _MODIFIER_KEY_RELATION_SAME
    return _MODIFIER_KEY_RELATION_DISTINCT


def _pair_signature_sha256(
    *,
    engine_binding_sha256: str,
    catalog_fingerprint: str,
    effect_signature_pair: tuple[str, str],
    modifier_key_relation: str,
    opaque_set_pair: tuple[str, ...],
) -> str:
    return _sha256(
        {
            "schema_version": GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION,
            "engine_binding_sha256": engine_binding_sha256,
            "catalog_fingerprint": catalog_fingerprint,
            "effect_signature_pair": list(effect_signature_pair),
            "modifier_key_relation": modifier_key_relation,
            "opaque_set_pair": list(opaque_set_pair),
        }
    )


def _package_set_key_pair(
    package: GcsimTwoPlusTwoTargetPackage,
) -> tuple[str, str]:
    return tuple(
        sorted((package.set_a.gcsim_set_key, package.set_b.gcsim_set_key))
    )


def _package_sort_key(
    package: GcsimTwoPlusTwoTargetPackage,
) -> tuple[str, str, str]:
    set_keys = _package_set_key_pair(package)
    return set_keys[0], set_keys[1], package.identity_sha256


def _group_sort_key(
    group: GcsimOptimizerTheoreticalPairGroup,
) -> tuple[str, ...]:
    return (
        *group.effect_signature_pair,
        group.modifier_key_relation,
        *(
            _package_set_key_pair(group.representative)
            if group.modifier_key_relation != _MODIFIER_KEY_RELATION_DISTINCT
            else ()
        ),
    )


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _require_sha256(value: object, field_name: str) -> None:
    if not _is_sha256(value):
        raise GcsimOptimizerTwoPieceSignatureError(
            f"{field_name} must be a SHA-256 digest"
        )


def _strip_go_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", " ", source)


def _sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "GCSIM_OPTIMIZER_TWO_PIECE_SIGNATURE_SCHEMA_VERSION",
    "GcsimOptimizerTheoreticalPairDomain",
    "GcsimOptimizerTheoreticalPairGroup",
    "GcsimOptimizerTwoPieceEffectDescriptor",
    "GcsimOptimizerTwoPieceProofKind",
    "GcsimOptimizerTwoPieceSignatureError",
    "build_gcsim_optimizer_guaranteed_two_piece_stat_effects",
    "build_gcsim_optimizer_theoretical_pair_domain",
    "build_gcsim_optimizer_two_piece_effect_descriptors",
]
