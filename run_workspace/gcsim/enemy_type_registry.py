"""Backend/dev GCSIM enemy target type registry and matcher.

This module parses known target type keys from local prepared GCSIM source
(`pkg/shortcut/enemies_gen.go`) when available, but tests pin the matcher with
small fixture registries. It is intentionally not a full hand-written monster
database and must not use fuzzy similarity as production truth.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GCSIM_SOURCE_ROOT = PROJECT_ROOT / "data" / "gcsim" / "sources" / "expanded"
GCSIM_ENEMY_SHORTCUT_RELATIVE_PATH = Path("pkg") / "shortcut" / "enemies_gen.go"

MATCH_METHOD_MANUAL_MAPPING = "manual_mapping"
MATCH_METHOD_EXACT_NORMALIZED_NAME = "exact_normalized_name"
MATCH_METHOD_COMPATIBLE_BASE_NAME = "compatible_base_name"
MATCH_METHOD_MANUAL_ALIAS = "manual_alias"
MATCH_METHOD_SNAP_TITLE_FALLBACK = "snap_title_fallback"
MATCH_METHOD_MISSING = "missing"
MATCH_METHOD_AMBIGUOUS = "ambiguous"

COMPATIBLE_VARIANT_TOKENS = (
    "battlehardened",
    "veteran",
)

_GO_MAP_KEY_PATTERN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"\s*:')


@dataclass(frozen=True, slots=True)
class GcsimEnemyNameCandidate:
    source_kind: str
    source_name: str

    @property
    def normalized_name(self) -> str:
        return normalize_gcsim_enemy_name(self.source_name)

    def to_dict(self) -> dict[str, str]:
        return {
            "source_kind": self.source_kind,
            "source_name": self.source_name,
            "normalized_name": self.normalized_name,
        }


@dataclass(frozen=True, slots=True)
class GcsimEnemyTypeMatch:
    method: str
    gcsim_type: str = ""
    selected_name: GcsimEnemyNameCandidate | None = None
    ambiguous_types: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.method in {
            MATCH_METHOD_EXACT_NORMALIZED_NAME,
            MATCH_METHOD_COMPATIBLE_BASE_NAME,
            MATCH_METHOD_MANUAL_ALIAS,
        } and bool(self.gcsim_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "gcsim_type": self.gcsim_type,
            "selected_name": None
            if self.selected_name is None
            else self.selected_name.to_dict(),
            "ambiguous_types": list(self.ambiguous_types),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class GcsimEnemyTypeRegistry:
    target_types: tuple[str, ...]
    source_path: str = ""
    manual_aliases: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        normalized_types = tuple(
            sorted({str(item).strip() for item in self.target_types if str(item).strip()})
        )
        object.__setattr__(self, "target_types", normalized_types)
        object.__setattr__(self, "source_path", str(self.source_path or ""))

    def match_name_candidates(
        self,
        candidates: tuple[GcsimEnemyNameCandidate, ...] | list[GcsimEnemyNameCandidate],
    ) -> GcsimEnemyTypeMatch:
        normalized_candidates = tuple(
            candidate
            for candidate in candidates
            if candidate.source_name and candidate.normalized_name
        )
        exact = self._match_exact(normalized_candidates)
        if exact is not None:
            return exact
        compatible = self._match_compatible(normalized_candidates)
        if compatible is not None:
            return compatible
        alias = self._match_alias(normalized_candidates)
        if alias is not None:
            return alias
        return GcsimEnemyTypeMatch(
            method=MATCH_METHOD_MISSING,
            warnings=("gcsim_enemy_type_match_missing",),
        )

    def _match_exact(
        self,
        candidates: tuple[GcsimEnemyNameCandidate, ...],
    ) -> GcsimEnemyTypeMatch | None:
        available = set(self.target_types)
        for candidate in candidates:
            if candidate.normalized_name in available:
                return GcsimEnemyTypeMatch(
                    method=MATCH_METHOD_EXACT_NORMALIZED_NAME,
                    gcsim_type=candidate.normalized_name,
                    selected_name=candidate,
                )
        return None

    def _match_compatible(
        self,
        candidates: tuple[GcsimEnemyNameCandidate, ...],
    ) -> GcsimEnemyTypeMatch | None:
        by_base: dict[str, list[str]] = defaultdict(list)
        for target_type in self.target_types:
            by_base[_compatible_base_name(target_type)].append(target_type)
        for candidate in candidates:
            base_name = _compatible_base_name(candidate.normalized_name)
            matches = tuple(sorted(set(by_base.get(base_name, []))))
            if not matches:
                continue
            if len(matches) == 1:
                return GcsimEnemyTypeMatch(
                    method=MATCH_METHOD_COMPATIBLE_BASE_NAME,
                    gcsim_type=matches[0],
                    selected_name=candidate,
                )
            return GcsimEnemyTypeMatch(
                method=MATCH_METHOD_AMBIGUOUS,
                selected_name=candidate,
                ambiguous_types=matches,
                warnings=(f"ambiguous_compatible_base_name:{base_name}",),
            )
        return None

    def _match_alias(
        self,
        candidates: tuple[GcsimEnemyNameCandidate, ...],
    ) -> GcsimEnemyTypeMatch | None:
        aliases = self.manual_aliases or {}
        available = set(self.target_types)
        for candidate in candidates:
            alias_target = aliases.get(candidate.normalized_name)
            if not alias_target:
                continue
            if alias_target not in available:
                return GcsimEnemyTypeMatch(
                    method=MATCH_METHOD_MISSING,
                    selected_name=candidate,
                    warnings=(f"manual_alias_target_missing:{alias_target}",),
                )
            return GcsimEnemyTypeMatch(
                method=MATCH_METHOD_MANUAL_ALIAS,
                gcsim_type=alias_target,
                selected_name=candidate,
            )
        return None


def normalize_gcsim_enemy_name(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def load_gcsim_enemy_type_registry_from_go_source(
    path: str | Path,
    *,
    manual_aliases: Mapping[str, str] | None = None,
) -> GcsimEnemyTypeRegistry:
    source_path = Path(path)
    text = source_path.read_text(encoding="utf-8")
    return GcsimEnemyTypeRegistry(
        target_types=tuple(_parse_go_map_string_keys(text)),
        source_path=str(source_path),
        manual_aliases=manual_aliases,
    )


def load_default_gcsim_enemy_type_registry(
    *,
    manual_aliases: Mapping[str, str] | None = None,
) -> GcsimEnemyTypeRegistry | None:
    source_path = find_default_gcsim_enemy_shortcut_source()
    if source_path is None:
        return None
    return load_gcsim_enemy_type_registry_from_go_source(
        source_path,
        manual_aliases=manual_aliases,
    )


def find_default_gcsim_enemy_shortcut_source() -> Path | None:
    if not DEFAULT_GCSIM_SOURCE_ROOT.is_dir():
        return None
    candidates = [
        path / GCSIM_ENEMY_SHORTCUT_RELATIVE_PATH
        for path in sorted(DEFAULT_GCSIM_SOURCE_ROOT.iterdir(), reverse=True)
        if path.is_dir()
    ]
    return next((path for path in candidates if path.is_file()), None)


def _parse_go_map_string_keys(text: str) -> tuple[str, ...]:
    keys: list[str] = []
    for match in _GO_MAP_KEY_PATTERN.finditer(text):
        key = match.group(1).encode("utf-8").decode("unicode_escape")
        normalized = str(key).strip()
        if normalized:
            keys.append(normalized)
    if "dummy" not in keys:
        keys.append("dummy")
    return tuple(sorted(set(keys)))


def _compatible_base_name(value: str) -> str:
    result = normalize_gcsim_enemy_name(value)
    changed = True
    while changed:
        changed = False
        for token in COMPATIBLE_VARIANT_TOKENS:
            if result.startswith(token) and len(result) > len(token):
                result = result[len(token):]
                changed = True
    return result
