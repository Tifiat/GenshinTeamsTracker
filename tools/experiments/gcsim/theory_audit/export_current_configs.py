"""Package reviewed current Theory point configs for independent GCSIM checks.

Owner: docs/optimizer-evidence/2026-10-03-theory-current-matrix/README.md.
This reads existing search/replay receipts. It runs no optimizer or simulator.
"""
from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping
import zipfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from run_workspace.gcsim.optimizer_engine_context import load_active_gcsim_optimizer_engine_context
from tools.experiments.gcsim.theory_audit import report_current_matrix as report
from tools.experiments.gcsim.theory_verification import run_case as base


OWNER = "docs/optimizer-evidence/2026-10-03-theory-current-matrix/README.md"
PROJECTION = report.OWNER / "reviewed_replay_bindings.json"
ARCHIVE = report.OUTPUTS / "Theory-current-configs-2026-10-03.zip"
ALL_TEAMS = tuple(team for team, _ in report.TEAMS)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _require_sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise ValueError(f"Invalid {label} SHA256")
    return value


def _relative_file(value: Any) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or Path(value).is_absolute():
        raise ValueError("Receipt path must be a canonical repository-relative path")
    path = base.inside_worker(value)
    if path.relative_to(ROOT).as_posix() != value or not path.is_file():
        raise ValueError(f"Missing or noncanonical receipt path: {value}")
    return path


def _same_sources(current: Mapping[str, Any], replay: Mapping[str, Any]) -> None:
    current_sources, replay_sources = current.get("source_sha256"), replay.get("source_sha256")
    if not isinstance(current_sources, dict) or not isinstance(replay_sources, dict):
        raise ValueError("Captured source hashes missing")
    shared = set(current_sources).intersection(replay_sources)
    if not shared or any(
        _require_sha(current_sources[key], f"current source {key}")
        != _require_sha(replay_sources[key], f"replay source {key}")
        for key in shared
    ):
        raise ValueError("Current search and replay were prepared from different shared sources")
    for source_map in (current_sources, replay_sources):
        for name, sha in source_map.items():
            _relative_file(name)
            _require_sha(sha, f"source {name}")


def _validate_records(
    team: str, current: Mapping[str, Any], replay: Mapping[str, Any], witness: Mapping[str, Any],
    *, active_engine_id: str, active_artifact_sha256: str,
) -> str:
    """Return exact saved config only when the current rank-one vector is bound."""
    rank_one = current["product"]["candidates"][0]
    point = replay["input"]["candidate"]
    current_binding, replay_binding = current["binding"], replay["binding"]
    request_engine = current_binding["request_engine"]
    current_input, replay_input = current["input"], replay["input"]
    if (
        type(rank_one.get("rank")) is not int or rank_one["rank"] != 1
        or type(point.get("rank")) is not int or point["rank"] != 1
        or rank_one["packages"] != point["packages"]
        or rank_one["allocations"] != point["allocations"]
        or witness.get("current_formula_dps") != rank_one["formula_dps"]
        or current_input["team"] != team or current_input["run_id"] != team + "_theory"
        or replay_input["team"] != team or replay_input["energy"] != "infinite"
        or current_input["manifest_sha256"] != replay_input["manifest_sha256"]
        or current_input["rotation_sha256"] != replay_input["rotation_sha256"]
        or current_binding["engine_id"] != replay_binding["engine_id"]
        or current_binding["engine_id"] != active_engine_id
        or current_binding["engine_artifact_sha256"] != replay_binding["artifact_sha256"]
        or current_binding["engine_artifact_sha256"] != active_artifact_sha256
        or request_engine["source_manifest_sha256"] != replay_binding["source_manifest_sha256"]
        or request_engine["patch_manifest_sha256"] != replay_binding["patch_manifest_sha256"]
        or request_engine["artifact_sha256"] != active_artifact_sha256
        or witness["ordinary_iterations"] != (500 if team == "gaming_melt" else 128)
    ):
        raise ValueError(f"Current Theory vector/runtime mismatch: {team}")
    if current_input["manifest_sha256"] != base.digest(base.MANIFEST):
        raise ValueError(f"Manifest file changed since current search: {team}")
    if current_input["rotation_sha256"] != base.digest(_relative_file(current_input["rotation_path"])):
        raise ValueError(f"Rotation file changed since current search: {team}")
    _same_sources(current, replay)
    config = replay_input["config_text"]
    if not isinstance(config, str) or base.text_digest(config) != replay_input["config_sha256"]:
        raise ValueError(f"Saved replay config hash changed: {team}")
    actors = re.findall(r"(?m)^([a-z][a-z0-9_]*) char [^;\r\n]+;[ \t]*$", config)
    profiles = current_input["profiles"]
    if len(actors) != 4 or actors != [row["character_key"] for row in profiles]:
        raise ValueError(f"Saved config declaration order differs from current profiles: {team}")
    for profile in profiles:
        key, weapon = profile["character_key"], profile["weapon_key"]
        weapon_rows = re.findall(rf"(?m)^{re.escape(key)} add weapon=\"([^\"\r\n]+)\" [^;\r\n]+;[ \t]*$", config)
        if weapon_rows != [weapon]:
            raise ValueError(f"Saved config weapon differs from current profile: {team}")
    if not re.search(r"(?m)^options [^;\r\n]*\bignore_burst_energy=true\b[^;\r\n]*;[ \t]*$", config):
        raise ValueError(f"Saved config energy mode differs from current Theory: {team}")
    return config


def _add(files: dict[str, bytes], name: str, payload: bytes) -> None:
    if name in files or name.startswith("/") or ".." in Path(name).parts or "\\" in name:
        raise ValueError(f"Duplicate or unsafe ZIP entry: {name}")
    files[name] = payload


def build_files(
    reviewed_teams: list[str], *, release_partial: bool = False,
    projection: Mapping[str, Any] | None = None,
) -> dict[str, bytes]:
    """Validate all receipts before producing any ZIP bytes or touching outputs."""
    if not reviewed_teams or len(set(reviewed_teams)) != len(reviewed_teams):
        raise ValueError("Explicit unique reviewed teams are required")
    chosen = set(reviewed_teams)
    if not chosen.issubset(ALL_TEAMS):
        raise ValueError("Unknown Theory team")
    supplied_projection = projection is not None
    if projection is None:
        projection = base.read_object(PROJECTION)
    projection_sha256 = base.canonical_digest(projection) if supplied_projection else base.digest(PROJECTION)
    if not isinstance(projection, Mapping) or projection.get("owner") != OWNER:
        raise ValueError("Current-matrix projection owner changed")
    projected = projection.get("current_teams")
    witnesses = projection.get("witnesses")
    if (
        not isinstance(projected, list) or len(set(projected)) != len(projected)
        or not isinstance(witnesses, dict)
        or chosen != set(projected) or chosen != set(witnesses)
    ):
        raise ValueError("Explicit team list differs from reviewed projection")
    if len(chosen) != len(ALL_TEAMS) and not release_partial:
        raise ValueError("Archive waits for all 14 reviewed teams or explicit partial release")
    active = load_active_gcsim_optimizer_engine_context()  # Read-only identity and artifact hash.
    files: dict[str, bytes] = {}
    rows = []
    for team in ALL_TEAMS:
        if team not in chosen:
            continue
        witness = witnesses[team]
        if not isinstance(witness, dict) or not witness.get("checks") or not all(witness["checks"].values()):
            raise ValueError(f"Unreviewed replay witness: {team}")
        current_path = report.receipt(team)
        if _require_sha(witness.get("current_search_sha256"), "current search") != base.digest(current_path):
            raise ValueError(f"Stale current search projection: {team}")
        current = report.reviewed(current_path, team)
        _, fresh_witness = report.replay_comparison(current, team)
        if fresh_witness is None or fresh_witness != witness:
            raise ValueError(f"Stale or unmatched replay projection: {team}")
        replay_path = _relative_file(witness.get("replay_path"))
        if _require_sha(witness.get("replay_sha256"), "replay") != base.digest(replay_path):
            raise ValueError(f"Stale replay receipt: {team}")
        replay = base.read_object(replay_path)
        config = _validate_records(
            team, current, replay, witness,
            active_engine_id=active.engine_id, active_artifact_sha256=active.artifact_sha256,
        )
        iterations = 500 if team == "gaming_melt" else 128
        exported = base.ordinary_options(config, iterations)
        name = f"{team}/config.txt"
        _add(files, name, exported.encode("utf-8"))
        rows.append({
            "team": team, "config_file": name, "ordinary_iterations": iterations,
            "exported_config_sha256": base.text_digest(exported),
            "saved_replay_config_sha256": base.text_digest(config),
            "current_search_path": current_path.relative_to(ROOT).as_posix(),
            "current_search_sha256": witness["current_search_sha256"],
            "replay_path": witness["replay_path"], "replay_sha256": witness["replay_sha256"],
            "engine_id": active.engine_id, "engine_artifact_sha256": active.artifact_sha256,
            "manifest_sha256": current["input"]["manifest_sha256"],
            "rotation_sha256": current["input"]["rotation_sha256"],
        })
    readme = (
        "# Конфигурации текущего Theory для GCSIM — 03.10.2026\n\n"
        "В папке каждой команды лежит config.txt с выбранными нынешним Theory "
        "сетами и распределением статов. Для обычного запуска GCSIM задано "
        "500 итераций у gaming_melt и 128 у остальных команд; workers=4. "
        "Персонажи, оружие, ротация, цель, сеты и статы сохранены из проверенной конфигурации.\n\n"
        "Эти артефакты виртуальные: дробные проки могут не соответствовать пяти "
        "реальным предметам. Энергия взрывов стихий бесконечная. Результат не "
        "доказывает глобально лучший набор. Для повторной проверки используйте "
        "совместимую версию GCSIM; её идентификатор и контрольная сумма записаны "
        "в checksums.json.\n\n"
        "Команды: " + ", ".join(row["team"] for row in rows) + "\n"
    )
    _add(files, "README.md", readme.encode("utf-8"))
    manifest = {
        "schema_version": 1, "owner": OWNER,
        "projection_path": PROJECTION.relative_to(ROOT).as_posix(),
        "projection_sha256": projection_sha256,
        "team_count": len(rows), "teams": rows,
        "readme_sha256": base.text_digest(readme),
    }
    _add(files, "checksums.json", (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))
    return files


def archive_bytes(files: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed", nargs="+", choices=ALL_TEAMS, required=True)
    parser.add_argument("--release-partial", action="store_true",
                        help="explicitly release fewer than all 14 reviewed teams")
    args = parser.parse_args(argv)
    if ARCHIVE.exists():
        raise FileExistsError(f"Refusing to replace existing Theory config archive: {ARCHIVE}")
    files = build_files(args.reviewed, release_partial=args.release_partial)
    payload = archive_bytes(files)
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHIVE.open("xb") as stream:
        stream.write(payload)
    print(json.dumps({"archive": str(ARCHIVE), "teams": len(files) - 2,
                      "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()},
                     ensure_ascii=True))


if __name__ == "__main__":
    main()
