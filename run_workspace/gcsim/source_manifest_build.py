"""One-time source-manifest preparation for a patched GCSIM engine build.

The analyzer lives in the patched engine and uses Go's parser.  This module
only supplies the immutable build binding, runs the analyzer once, and checks
that its body did not rewrite any of the supplied identity inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
from typing import Callable, Mapping, Sequence


SOURCE_MANIFEST_INPUT_SCHEMA_VERSION = 1
SOURCE_MANIFEST_INPUT_KIND = "gtt.source_manifest.binding_input"
SOURCE_MANIFEST_BODY_SCHEMA_VERSION = 1
SOURCE_MANIFEST_BODY_KIND = "gtt.source_manifest.body"
SOURCE_MANIFEST_TRACE_SCHEMA_VERSION = 6
SOURCE_MANIFEST_TRACE_CAPABILITY = "gtt_trace_equation_v6"
SOURCE_MANIFEST_ENGINE_CAPABILITY = "gtt_source_manifest_v1"
SOURCE_MANIFEST_COMMAND_RELATIVE_PATH = Path("cmd") / "gtt-source-manifest"
SOURCE_MANIFEST_INPUT_RELATIVE_PATH = Path("build") / "gtt-source-manifest-input.json"
SOURCE_MANIFEST_BODY_RELATIVE_PATH = Path("build") / "gtt-source-manifest-body.json"
SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH = (
    Path("pkg") / "gttsource" / "generated_manifest.go"
)
SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH = Path("build") / "gtt-source-overlay.json"
SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH = Path("build") / "gtt-source-overlay"

_BASE_INPUT_KEYS = {
    "schema_version",
    "kind",
    "upstream_repo",
    "upstream_ref",
    "pristine_source_tree_sha256",
    "patches",
    "patch_stack_sha256",
    "trace_schema_version",
    "trace_capability",
    "formula_identities",
}
_COMPLETE_INPUT_KEYS = _BASE_INPUT_KEYS | {"go_toolchain", "build_flags"}
_BODY_KEYS = _COMPLETE_INPUT_KEYS | {
    "compiler_version",
    "patched_source_tree_sha256",
    "entries",
}

ManifestRunner = Callable[
    [Sequence[str], Path, Mapping[str, str], int],
    subprocess.CompletedProcess[str],
]


@dataclass(frozen=True, slots=True)
class SourceManifestPreparation:
    required: bool
    ready: bool
    status: str
    command: tuple[str, ...] = ()
    stdout: str = ""
    stderr: str = ""
    input_relative_path: str = ""
    body_relative_path: str = ""
    generated_go_relative_path: str = ""
    overlay_relative_path: str = ""
    overlay_dir_relative_path: str = ""
    body_sha256: str = ""
    compiler_version: str = ""
    patched_source_tree_sha256: str = ""
    error: str = ""


def engine_requires_source_manifest(engine_dir: str | Path) -> bool:
    command_dir = Path(engine_dir) / SOURCE_MANIFEST_COMMAND_RELATIVE_PATH
    return command_dir.is_dir() and (command_dir / "main.go").is_file()


def prepare_source_manifest(
    engine_dir: str | Path,
    *,
    binding_input: Mapping[str, object] | None,
    go_version: str,
    go_os: str,
    go_arch: str,
    go_executable: str,
    env: Mapping[str, str],
    timeout_seconds: int,
    runner: ManifestRunner,
) -> SourceManifestPreparation:
    engine_dir = Path(engine_dir)
    if not engine_requires_source_manifest(engine_dir):
        return SourceManifestPreparation(
            required=False,
            ready=False,
            status="not_required",
        )
    if binding_input is None:
        return _failure("binding_input_missing", "Source manifest binding input is required.")
    try:
        complete_input = complete_source_manifest_binding_input(
            binding_input,
            go_version=go_version,
            go_os=go_os,
            go_arch=go_arch,
        )
    except (TypeError, ValueError) as exc:
        return _failure("binding_input_invalid", str(exc))

    input_path = engine_dir / SOURCE_MANIFEST_INPUT_RELATIVE_PATH
    body_path = engine_dir / SOURCE_MANIFEST_BODY_RELATIVE_PATH
    go_output_path = engine_dir / SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH
    overlay_path = engine_dir / SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH
    overlay_dir = engine_dir / SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH
    input_path.parent.mkdir(parents=True, exist_ok=True)
    go_output_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(canonical_json(complete_input) + "\n", encoding="utf-8")

    command = (
        str(go_executable),
        "run",
        "./cmd/gtt-source-manifest",
        "-root",
        ".",
        "-binding-in",
        SOURCE_MANIFEST_INPUT_RELATIVE_PATH.as_posix(),
        "-json-out",
        SOURCE_MANIFEST_BODY_RELATIVE_PATH.as_posix(),
        "-go-out",
        SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH.as_posix(),
        "-overlay-out",
        SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH.as_posix(),
        "-overlay-dir",
        SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH.as_posix(),
    )
    try:
        result = runner(command, engine_dir, env, int(timeout_seconds))
    except subprocess.TimeoutExpired as exc:
        return _failure(
            "source_manifest_timeout",
            "GCSIM source-manifest generation timed out.",
            command=command,
            stdout=exc.stdout if isinstance(exc.stdout, str) else "",
            stderr=exc.stderr if isinstance(exc.stderr, str) else "",
        )
    except OSError as exc:
        return _failure(
            "source_manifest_failed",
            str(exc),
            command=command,
        )
    if result.returncode != 0:
        return _failure(
            "source_manifest_failed",
            f"GCSIM source-manifest generator exited with {result.returncode}.",
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    if (
        not body_path.is_file()
        or not go_output_path.is_file()
        or not overlay_path.is_file()
        or not overlay_dir.is_dir()
    ):
        return _failure(
            "source_manifest_output_missing",
            "Source-manifest generator did not create all required manifest and overlay outputs.",
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    try:
        body = json.loads(body_path.read_text(encoding="utf-8"))
        _validate_body(
            body,
            complete_input,
            expected_patched_tree_sha256=compute_patched_source_tree_sha256(engine_dir),
        )
        _validate_strict_body_contract(body)
        _validate_overlay(engine_dir, overlay_path, overlay_dir)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return _failure(
            "source_manifest_output_invalid",
            str(exc),
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    canonical_body = canonical_json(body)
    body_path.write_text(canonical_body + "\n", encoding="utf-8")
    body_sha256 = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
    return SourceManifestPreparation(
        required=True,
        ready=True,
        status="source_manifest_passed",
        command=tuple(command),
        stdout=str(result.stdout or "").strip(),
        stderr=str(result.stderr or "").strip(),
        input_relative_path=SOURCE_MANIFEST_INPUT_RELATIVE_PATH.as_posix(),
        body_relative_path=SOURCE_MANIFEST_BODY_RELATIVE_PATH.as_posix(),
        generated_go_relative_path=SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH.as_posix(),
        overlay_relative_path=SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH.as_posix(),
        overlay_dir_relative_path=SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH.as_posix(),
        body_sha256=body_sha256,
        compiler_version=str(body["compiler_version"]),
        patched_source_tree_sha256=str(body["patched_source_tree_sha256"]),
    )


def complete_source_manifest_binding_input(
    binding_input: Mapping[str, object],
    *,
    go_version: str,
    go_os: str,
    go_arch: str,
) -> dict[str, object]:
    if not isinstance(binding_input, Mapping):
        raise TypeError("source manifest binding input must be an object")
    row = dict(binding_input)
    if set(row) != _BASE_INPUT_KEYS:
        raise ValueError("source manifest binding input keys do not match schema v1")
    if row["schema_version"] != SOURCE_MANIFEST_INPUT_SCHEMA_VERSION:
        raise ValueError("unsupported source manifest binding schema")
    if row["kind"] != SOURCE_MANIFEST_INPUT_KIND:
        raise ValueError("unsupported source manifest binding kind")
    _require_trimmed(row["upstream_repo"], "upstream_repo")
    _require_trimmed(row["upstream_ref"], "upstream_ref")
    _require_sha256(row["pristine_source_tree_sha256"], "pristine_source_tree_sha256")
    _validate_ordered_hash_rows(row["patches"], "patches")
    _require_sha256(row["patch_stack_sha256"], "patch_stack_sha256")
    expected_patch_stack = hashlib.sha256(
        canonical_json(
            {"schema_version": 1, "patches": row["patches"]}
        ).encode("utf-8")
    ).hexdigest()
    if row["patch_stack_sha256"] != expected_patch_stack:
        raise ValueError("patch_stack_sha256 does not match ordered patch rows")
    if row["trace_schema_version"] != SOURCE_MANIFEST_TRACE_SCHEMA_VERSION:
        raise ValueError("source manifest trace schema must be 6")
    if row["trace_capability"] != SOURCE_MANIFEST_TRACE_CAPABILITY:
        raise ValueError("source manifest trace capability mismatch")
    _validate_ordered_hash_rows(row["formula_identities"], "formula_identities", key="id")
    _require_trimmed(go_version, "go_version")
    _require_trimmed(go_os, "go_os")
    _require_trimmed(go_arch, "go_arch")
    row["go_toolchain"] = {
        "version": go_version,
        "os": go_os,
        "arch": go_arch,
    }
    row["build_flags"] = ["-trimpath"]
    return row


def canonical_json(value: object) -> str:
    output: list[str] = []
    _append_canonical_json(output, value)
    return "".join(output)


def _append_canonical_json(output: list[str], value: object) -> None:
    if value is None:
        output.append("null")
    elif value is True:
        output.append("true")
    elif value is False:
        output.append("false")
    elif isinstance(value, str):
        output.append(json.dumps(value, ensure_ascii=True, allow_nan=False))
    elif isinstance(value, int):
        output.append(str(value))
    elif isinstance(value, float):
        output.append(_go_json_float(value))
    elif isinstance(value, (list, tuple)):
        output.append("[")
        for index, item in enumerate(value):
            if index:
                output.append(",")
            _append_canonical_json(output, item)
        output.append("]")
    elif isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical source manifest object keys must be strings")
        output.append("{")
        for index, key in enumerate(sorted(value)):
            if index:
                output.append(",")
            output.append(json.dumps(key, ensure_ascii=True, allow_nan=False))
            output.append(":")
            _append_canonical_json(output, value[key])
        output.append("}")
    else:
        raise TypeError(f"unsupported canonical source manifest value {type(value)!r}")


def _go_json_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite source manifest number")
    if value == 0.0:
        return "-0" if math.copysign(1.0, value) < 0.0 else "0"
    absolute = abs(value)
    shortest = repr(value).lower()
    if 1e-6 <= absolute < 1e21:
        rendered = format(Decimal(shortest), "f") if "e" in shortest else shortest
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered
    if "e" not in shortest:
        shortest = format(Decimal(shortest).normalize(), "e")
    mantissa, exponent_text = shortest.split("e", 1)
    if "." in mantissa:
        mantissa = mantissa.rstrip("0").rstrip(".")
    exponent = int(exponent_text)
    exponent_suffix = f"+{exponent}" if exponent >= 0 else str(exponent)
    return f"{mantissa}e{exponent_suffix}"


def compute_patched_source_tree_sha256(engine_dir: str | Path) -> str:
    """Hash the exact patched module inputs without generated self-references."""

    engine_root = Path(engine_dir).resolve()
    rows: list[dict[str, str]] = []
    generated_go = SOURCE_MANIFEST_GENERATED_GO_RELATIVE_PATH.as_posix()
    for current_root, directory_names, file_names in os.walk(
        engine_root,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name not in {".git", "build"}
            and not (current / name).is_symlink()
        )
        for file_name in sorted(file_names):
            path = current / file_name
            if path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(engine_root).as_posix()
            if relative == generated_go:
                continue
            rows.append({"path": relative, "sha256": _file_sha256(path)})
    rows.sort(key=lambda row: row["path"])
    canonical = canonical_json({"schema_version": 1, "files": rows})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_body(
    body: object,
    expected_input: Mapping[str, object],
    *,
    expected_patched_tree_sha256: str,
) -> None:
    if not isinstance(body, dict) or set(body) != _BODY_KEYS:
        raise ValueError("source manifest body keys do not match schema v1")
    if body["schema_version"] != SOURCE_MANIFEST_BODY_SCHEMA_VERSION:
        raise ValueError("unsupported source manifest body schema")
    if body["kind"] != SOURCE_MANIFEST_BODY_KIND:
        raise ValueError("unsupported source manifest body kind")
    for key in _COMPLETE_INPUT_KEYS - {"kind"}:
        if body[key] != expected_input[key]:
            raise ValueError(f"source manifest body changed bound field: {key}")
    _require_trimmed(body["compiler_version"], "compiler_version")
    _require_sha256(body["patched_source_tree_sha256"], "patched_source_tree_sha256")
    if body["patched_source_tree_sha256"] != expected_patched_tree_sha256:
        raise ValueError(
            "patched_source_tree_sha256 does not match independently hashed source tree"
        )
    if not isinstance(body["entries"], list):
        raise ValueError("source manifest entries must be an array")


def _validate_strict_body_contract(body: Mapping[str, object]) -> None:
    """Reject a build that the optimizer's runtime V6 decoder cannot consume."""

    from .trace_equation.source_dependencies import (
        decode_source_manifest_body,
        encode_source_manifest_body,
    )

    canonical = canonical_json(body)
    decoded = decode_source_manifest_body(canonical)
    if encode_source_manifest_body(decoded) != canonical:
        raise ValueError(
            "source manifest strict decoder did not preserve canonical body bytes"
        )


def _validate_overlay(engine_dir: Path, overlay_path: Path, overlay_dir: Path) -> None:
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    if not isinstance(overlay, dict) or set(overlay) != {"Replace"}:
        raise ValueError("source overlay must contain only the Go Replace map")
    replacements = overlay["Replace"]
    if not isinstance(replacements, dict) or not replacements:
        raise ValueError("source overlay Replace map must be non-empty")

    engine_root = engine_dir.resolve()
    replacement_root = overlay_dir.resolve()
    for original_text, replacement_text in replacements.items():
        if not isinstance(original_text, str) or not isinstance(replacement_text, str):
            raise ValueError("source overlay paths must be strings")
        original = Path(original_text)
        replacement = Path(replacement_text)
        if not original.is_absolute() or not replacement.is_absolute():
            raise ValueError("source overlay paths must be absolute")
        original = original.resolve()
        replacement = replacement.resolve()
        if not original.is_relative_to(engine_root) or not original.is_file():
            raise ValueError("source overlay original must be a regular file inside engine root")
        if not replacement.is_relative_to(replacement_root) or not replacement.is_file():
            raise ValueError(
                "source overlay replacement must be a regular file inside overlay directory"
            )
        if original == replacement:
            raise ValueError("source overlay replacement must differ from its original")


def _validate_ordered_hash_rows(value: object, field: str, *, key: str = "path") -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    seen: set[str] = set()
    for index, raw in enumerate(value):
        if not isinstance(raw, dict) or set(raw) != {key, "sha256"}:
            raise ValueError(f"{field}[{index}] has invalid keys")
        name = raw[key]
        _require_trimmed(name, f"{field}[{index}].{key}")
        if name in seen:
            raise ValueError(f"{field} contains duplicate {key}")
        seen.add(name)
        _require_sha256(raw["sha256"], f"{field}[{index}].sha256")


def _require_trimmed(value: object, field: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be a non-empty trimmed string")


def _require_sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _failure(
    status: str,
    error: str,
    *,
    command: Sequence[str] = (),
    stdout: str = "",
    stderr: str = "",
) -> SourceManifestPreparation:
    return SourceManifestPreparation(
        required=True,
        ready=False,
        status=status,
        command=tuple(str(part) for part in command),
        stdout=str(stdout or "").strip(),
        stderr=str(stderr or "").strip(),
        error=str(error or "").strip(),
    )


__all__ = [
    "SOURCE_MANIFEST_BODY_KIND",
    "SOURCE_MANIFEST_BODY_RELATIVE_PATH",
    "SOURCE_MANIFEST_INPUT_KIND",
    "SOURCE_MANIFEST_ENGINE_CAPABILITY",
    "SOURCE_MANIFEST_OVERLAY_DIR_RELATIVE_PATH",
    "SOURCE_MANIFEST_OVERLAY_RELATIVE_PATH",
    "SOURCE_MANIFEST_TRACE_CAPABILITY",
    "SOURCE_MANIFEST_TRACE_SCHEMA_VERSION",
    "SourceManifestPreparation",
    "canonical_json",
    "compute_patched_source_tree_sha256",
    "complete_source_manifest_binding_input",
    "engine_requires_source_manifest",
    "prepare_source_manifest",
]
