"""Engine-scoped artifact-set capability catalog for optimizer search.

The farming search must not equate a parser shortcut with a modeled set bonus.
This module reads the implementation packages and upstream issue metadata from
one prepared GCSIM source tree. It is intentionally source-backed: a bare binary
without the matching source/issue snapshot is not sufficient provenance for a
new search catalog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_CONFIG_KEY_RE = re.compile(r"(?m)^\s*key\s*:\s*([^\s#]+)\s*$")
_REGISTER_RE = re.compile(r"\bcore\.RegisterSetFunc\s*\(")
_REGISTER_KEY_RE = re.compile(
    r"\bcore\.RegisterSetFunc\s*\(\s*keys\.(?P<key>[A-Za-z0-9_]+)\s*,"
)
_FOUR_PIECE_MARKER_RE = re.compile(
    r"\bcount\s*(?:>=|<=|==|>|<)\s*4\b",
    re.IGNORECASE,
)
_TWO_PIECE_MARKER_RE = re.compile(
    r"\bcount\s*(?:>=|<=|==|>|<)\s*2\b",
    re.IGNORECASE,
)
_FOUR_PIECE_NOT_IMPLEMENTED_RE = re.compile(
    r"(?:4\s*(?:pc|piece)[^\n]{0,100}not implemented|"
    r"not implemented[^\n]{0,100}4\s*(?:pc|piece))",
    re.IGNORECASE,
)
_TWO_PIECE_NOT_IMPLEMENTED_RE = re.compile(
    r"(?:2\s*(?:pc|piece)[^\n]{0,100}not implemented|"
    r"not implemented[^\n]{0,100}2\s*(?:pc|piece))",
    re.IGNORECASE,
)

_ARTIFACTS_RELATIVE_DIR = Path("internal") / "artifacts"
_ISSUES_RELATIVE_PATH = (
    Path("ui")
    / "packages"
    / "docs"
    / "src"
    / "components"
    / "Issues"
    / "artifact_data.json"
)
_OPTIMIZER_SUBSTATS_RELATIVE_PATH = Path("pkg") / "optimization" / "substats.go"
_FOUR_STAR_SET_BLOCK_RE = re.compile(
    r"artifactSets4Star\s*=\s*\[\]keys\.Set\s*\{(?P<body>.*?)\}",
    re.DOTALL,
)
_KEY_CONSTANT_RE = re.compile(r"\bkeys\.([A-Za-z0-9_]+)\b")
_SET_PARAMETER_KEY_RE = re.compile(r"\bparam\s*\[\s*\"(?P<key>[a-zA-Z0-9_]+)\"\s*\]")


class GcsimArtifactSetCatalogError(RuntimeError):
    """Raised when a source tree cannot provide a trustworthy set catalog."""


@dataclass(frozen=True, slots=True)
class GcsimArtifactSetCapability:
    key: str
    package_name: str
    key_constant: str
    max_rarity: int
    registered: bool
    has_two_piece_code: bool
    has_four_piece_code: bool
    two_piece_modeled: bool
    four_piece_modeled: bool
    issues: tuple[str, ...] = ()
    source_files: tuple[str, ...] = ()
    parameter_keys: tuple[str, ...] = ()

    @property
    def complete_four_piece_modeled(self) -> bool:
        """Whether wearing four pieces applies both requested bonus tiers."""

        return self.two_piece_modeled and self.four_piece_modeled

    @property
    def optimizer_four_piece_ready(self) -> bool:
        """Whether Phase-1 can render the complete package without set params."""

        return self.complete_four_piece_modeled and not self.parameter_keys

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "package_name": self.package_name,
            "key_constant": self.key_constant,
            "max_rarity": self.max_rarity,
            "registered": self.registered,
            "has_two_piece_code": self.has_two_piece_code,
            "has_four_piece_code": self.has_four_piece_code,
            "two_piece_modeled": self.two_piece_modeled,
            "four_piece_modeled": self.four_piece_modeled,
            "complete_four_piece_modeled": self.complete_four_piece_modeled,
            "optimizer_four_piece_ready": self.optimizer_four_piece_ready,
            "parameter_keys": list(self.parameter_keys),
            "issues": list(self.issues),
            "source_files": list(self.source_files),
        }


@dataclass(frozen=True, slots=True)
class GcsimArtifactSetCatalog:
    source_root: str
    source_fingerprint: str
    sets: tuple[GcsimArtifactSetCapability, ...] = ()
    warnings: tuple[str, ...] = ()
    _by_key: Mapping[str, GcsimArtifactSetCapability] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        immutable_sets = tuple(self.sets)
        immutable_warnings = tuple(self.warnings)
        lookup: dict[str, GcsimArtifactSetCapability] = {}
        for item in immutable_sets:
            normalized_key = str(item.key).strip().casefold()
            if not normalized_key:
                raise GcsimArtifactSetCatalogError(
                    "Artifact set catalog contains an empty key."
                )
            if normalized_key in lookup:
                raise GcsimArtifactSetCatalogError(
                    "Artifact set catalog contains a duplicate normalized key: "
                    f"{normalized_key}"
                )
            lookup[normalized_key] = item
        object.__setattr__(self, "sets", immutable_sets)
        object.__setattr__(self, "warnings", immutable_warnings)
        object.__setattr__(self, "_by_key", MappingProxyType(lookup))

    def get(self, key: str) -> GcsimArtifactSetCapability | None:
        return self._by_key.get(str(key).strip().casefold())

    @property
    def modeled_four_piece_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.sets
            if item.complete_four_piece_modeled
        )

    @property
    def modeled_two_piece_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.sets if item.two_piece_modeled)

    @property
    def optimizer_ready_four_piece_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.sets
            if item.optimizer_four_piece_ready
        )

    @property
    def modeled_five_star_four_piece_keys(self) -> tuple[str, ...]:
        return tuple(
            item.key
            for item in self.sets
            if item.complete_four_piece_modeled and item.max_rarity == 5
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_root": self.source_root,
            "source_fingerprint": self.source_fingerprint,
            "sets": [item.to_dict() for item in self.sets],
            "warnings": list(self.warnings),
        }


def load_gcsim_artifact_set_catalog(
    source_root: str | Path,
    *,
    require_issue_metadata: bool = True,
    require_optimizer_metadata: bool = True,
) -> GcsimArtifactSetCatalog:
    """Load modeled 2p/4p capabilities from one prepared engine source tree."""

    root = Path(source_root).expanduser().resolve()
    artifacts_dir = root / _ARTIFACTS_RELATIVE_DIR
    if not artifacts_dir.is_dir():
        raise GcsimArtifactSetCatalogError(
            f"GCSIM artifact implementation directory is missing: {artifacts_dir}"
        )

    issue_path = root / _ISSUES_RELATIVE_PATH
    if require_issue_metadata and not issue_path.is_file():
        raise GcsimArtifactSetCatalogError(
            f"GCSIM artifact issue metadata is missing: {issue_path}"
        )
    issue_map, issue_warnings = _load_issue_map(issue_path)
    optimizer_substats_path = root / _OPTIMIZER_SUBSTATS_RELATIVE_PATH
    if require_optimizer_metadata and not optimizer_substats_path.is_file():
        raise GcsimArtifactSetCatalogError(
            f"GCSIM optimizer set-rarity metadata is missing: {optimizer_substats_path}"
        )
    four_star_constants, optimizer_warnings = _load_four_star_set_constants(
        optimizer_substats_path
    )

    capabilities: list[GcsimArtifactSetCapability] = []
    fingerprint_files: list[Path] = []
    for package_dir in sorted(
        (path for path in artifacts_dir.iterdir() if path.is_dir()),
        key=lambda path: path.name.casefold(),
    ):
        config_path = package_dir / "config.yml"
        if not config_path.is_file():
            continue
        config_text = config_path.read_text(encoding="utf-8")
        match = _CONFIG_KEY_RE.search(config_text)
        if match is None:
            raise GcsimArtifactSetCatalogError(
                f"Artifact package has no config key: {config_path}"
            )
        key = match.group(1).strip().casefold()
        go_files = tuple(
            sorted(
                (
                    path
                    for path in package_dir.glob("*.go")
                    if not path.name.endswith("_test.go")
                ),
                key=lambda path: path.name,
            )
        )
        source_text = "\n".join(
            _strip_go_comments(
                path.read_text(encoding="utf-8", errors="replace")
            )
            for path in go_files
        )
        register_match = _REGISTER_KEY_RE.search(source_text)
        key_constant = register_match.group("key") if register_match is not None else ""
        metadata_issues = tuple(str(item) for item in issue_map.get(key, ()))
        explicit_issues = _explicit_not_implemented_issues(source_text)
        issues = _dedupe((*metadata_issues, *explicit_issues))
        registered = bool(_REGISTER_RE.search(source_text))
        has_two_piece_code = bool(_TWO_PIECE_MARKER_RE.search(source_text))
        has_four_piece_code = bool(_FOUR_PIECE_MARKER_RE.search(source_text))
        two_piece_blocked = any(_mentions_unimplemented(issue, piece=2) for issue in issues)
        four_piece_blocked = any(_mentions_unimplemented(issue, piece=4) for issue in issues)
        source_files = tuple(
            path.relative_to(root).as_posix() for path in (config_path, *go_files)
        )
        capabilities.append(
            GcsimArtifactSetCapability(
                key=key,
                package_name=package_dir.name,
                key_constant=key_constant,
                max_rarity=4 if key_constant in four_star_constants else 5,
                registered=registered,
                has_two_piece_code=has_two_piece_code,
                has_four_piece_code=has_four_piece_code,
                two_piece_modeled=(registered and has_two_piece_code and not two_piece_blocked),
                four_piece_modeled=(registered and has_four_piece_code and not four_piece_blocked),
                issues=issues,
                source_files=source_files,
                parameter_keys=tuple(
                    sorted(
                        {
                            match.group("key").casefold()
                            for match in _SET_PARAMETER_KEY_RE.finditer(source_text)
                        }
                    )
                ),
            )
        )
        fingerprint_files.extend((config_path, *go_files))

    if issue_path.is_file():
        fingerprint_files.append(issue_path)
    if optimizer_substats_path.is_file():
        fingerprint_files.append(optimizer_substats_path)
    return GcsimArtifactSetCatalog(
        source_root=str(root),
        source_fingerprint=_fingerprint(root, fingerprint_files),
        sets=tuple(capabilities),
        warnings=_dedupe((*issue_warnings, *optimizer_warnings)),
    )


def _load_issue_map(path: Path) -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    if not path.is_file():
        return {}, ("artifact_issue_metadata_missing",)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GcsimArtifactSetCatalogError(
            f"Could not parse GCSIM artifact issue metadata {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise GcsimArtifactSetCatalogError(
            f"GCSIM artifact issue metadata root must be an object: {path}"
        )
    result: dict[str, tuple[str, ...]] = {}
    warnings: list[str] = []
    for raw_key, raw_issues in payload.items():
        key = str(raw_key).strip().casefold()
        if not isinstance(raw_issues, list):
            warnings.append(f"artifact_issue_entry_invalid:{key}")
            continue
        result[key] = tuple(str(item) for item in raw_issues)
    return result, tuple(warnings)


def _load_four_star_set_constants(path: Path) -> tuple[set[str], tuple[str, ...]]:
    if not path.is_file():
        return set(), ("optimizer_set_rarity_metadata_missing",)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GcsimArtifactSetCatalogError(
            f"Could not read GCSIM optimizer set-rarity metadata {path}: {exc}"
        ) from exc
    match = _FOUR_STAR_SET_BLOCK_RE.search(source)
    if match is None:
        raise GcsimArtifactSetCatalogError(
            f"Could not identify artifactSets4Star in {path}"
        )
    return set(_KEY_CONSTANT_RE.findall(match.group("body"))), ()


def _explicit_not_implemented_issues(source_text: str) -> tuple[str, ...]:
    issues: list[str] = []
    if _TWO_PIECE_NOT_IMPLEMENTED_RE.search(source_text):
        issues.append("2pc is explicitly marked not implemented in source")
    if _FOUR_PIECE_NOT_IMPLEMENTED_RE.search(source_text):
        issues.append("4pc is explicitly marked not implemented in source")
    return tuple(issues)


def _mentions_unimplemented(issue: str, *, piece: int) -> bool:
    normalized = " ".join(str(issue).casefold().split())
    marker = re.compile(rf"\b{piece}\s*(?:pc|piece)\b")
    return "not implemented" in normalized and marker.search(normalized) is not None


def _strip_go_comments(source: str) -> str:
    """Remove Go comments while preserving quoted and raw string contents."""

    output: list[str] = []
    index = 0
    state = "code"
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char == "/" and nxt == "/":
                state = "line_comment"
                output.extend((" ", " "))
                index += 2
                continue
            if char == "/" and nxt == "*":
                state = "block_comment"
                output.extend((" ", " "))
                index += 2
                continue
            output.append(char)
            if char == '"':
                state = "quoted_string"
            elif char == "'":
                state = "rune"
            elif char == "`":
                state = "raw_string"
            index += 1
            continue
        if state == "line_comment":
            if char in "\r\n":
                output.append(char)
                state = "code"
            else:
                output.append(" ")
            index += 1
            continue
        if state == "block_comment":
            if char == "*" and nxt == "/":
                output.extend((" ", " "))
                state = "code"
                index += 2
            else:
                output.append(char if char in "\r\n" else " ")
                index += 1
            continue
        output.append(char)
        if state in {"quoted_string", "rune"} and char == "\\":
            if index + 1 < len(source):
                output.append(source[index + 1])
                index += 2
            else:
                index += 1
            continue
        if (
            (state == "quoted_string" and char == '"')
            or (state == "rune" and char == "'")
            or (state == "raw_string" and char == "`")
        ):
            state = "code"
        index += 1
    return "".join(output)


def _fingerprint(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
