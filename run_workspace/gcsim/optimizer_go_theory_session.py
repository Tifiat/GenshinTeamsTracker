"""Live Theory snapshots and commands over the existing process lifecycle.

The native process owns grouping, feasibility and continuation. This adapter
only validates result identity, copies snapshots and sends explicit commands.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Mapping
from uuid import uuid4

from .optimizer_go_requests import GcsimOptimizerGoError
from .optimizer_go_theory import (
    GcsimOptimizerGoTheoryRequest,
    GcsimOptimizerGoTheorySession as _LegacyTheorySession,
)
from .optimizer_go_result_text import format_optimizer_warning
from .optimizer_theory_presentation import theory_measurement, validate_theory_family


GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND = "gtt_gcsim_optimizer_theory_result_v3"
THEORY_SESSION_COMMAND_KIND = "gtt_theory_session_command_v1"
THEORY_SESSION_PHASES = frozenset({"first_light", "breadth_light", "deep_baseline"})
_THEORY_PHASE_ORDER = {"first_light": 0, "breadth_light": 1, "deep_baseline": 2}
_VERIFICATION_FIELDS = (
    "limit", "iterations", "attempted_count", "completed_count", "failed_count",
    "energy_rejected_count", "candidate_count", "unverified_count", "omitted_count",
    "remaining_budget", "in_progress",
)


def copy_theory_snapshot(
    value: Mapping[str, Any],
    *,
    expected_request_sha256: str = "",
    expected_session_id: str = "",
    newer_than: int = 0,
    previous_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate wire identity and return a detached snapshot without reranking."""
    if not isinstance(value, Mapping):
        raise GcsimOptimizerGoError("theory_snapshot_invalid", "Theory snapshot is not an object.")
    try:
        snapshot = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise GcsimOptimizerGoError("theory_snapshot_invalid", "Theory snapshot is not valid JSON.") from exc
    if (
        type(snapshot.get("schema_version")) is not int
        or snapshot["schema_version"] != 3
        or snapshot.get("schema_kind") != GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND
        or snapshot.get("status") not in {"success", "no_verified_result"}
    ):
        raise GcsimOptimizerGoError("theory_snapshot_invalid", "Theory snapshot schema does not match the application.")
    request_sha = snapshot.get("request_sha256")
    session_id = snapshot.get("session_id")
    if (
        not isinstance(request_sha, str) or not request_sha
        or not isinstance(session_id, str) or not session_id
        or (expected_request_sha256 and request_sha != expected_request_sha256)
        or (expected_session_id and session_id != expected_session_id)
    ):
        raise GcsimOptimizerGoError("theory_snapshot_identity_mismatch", "Theory snapshot belongs to another request or session.")
    search_version = snapshot.get("snapshot_version")
    publication_version = snapshot.get("publication_version")
    if type(search_version) is not int or search_version < 1:
        raise GcsimOptimizerGoError("theory_snapshot_invalid", "Theory snapshot has an invalid search version.")
    if type(publication_version) is not int or publication_version <= newer_than:
        raise GcsimOptimizerGoError("theory_snapshot_stale", "Theory publication is not newer than the displayed result.")
    if not isinstance(snapshot.get("phase"), str) or snapshot["phase"] not in THEORY_SESSION_PHASES:
        raise GcsimOptimizerGoError("theory_snapshot_invalid", "Theory snapshot has an unknown phase.")
    if previous_snapshot is not None and (
        search_version < previous_snapshot.get("snapshot_version", 0)
        or _THEORY_PHASE_ORDER[snapshot["phase"]]
        < _THEORY_PHASE_ORDER.get(previous_snapshot.get("phase"), -1)
    ):
        raise GcsimOptimizerGoError("theory_snapshot_stale", "Theory search snapshot or phase moved backwards.")
    for field in ("reference_score", "practical_band_percent", "sensitivity_band_percent"):
        number = snapshot.get(field)
        if not _nonnegative_number(number):
            raise GcsimOptimizerGoError("theory_snapshot_invalid", f"Theory snapshot has an invalid {field}.")
    for field in ("co_leaders", "pending", "unavailable"):
        if not isinstance(snapshot.get(field), list):
            raise GcsimOptimizerGoError("theory_snapshot_invalid", f"Theory snapshot has no {field} list.")
    verification = snapshot.get("verification")
    if not isinstance(verification, dict) or any(
        type(verification.get(field)) is not int or verification[field] < 0
        for field in _VERIFICATION_FIELDS
        if field != "in_progress"
    ):
        _invalid_snapshot("has invalid verification counts")
    if not isinstance(verification.get("policy_id"), str) or not verification["policy_id"].strip():
        _invalid_snapshot("has no verification policy identity")
    if type(verification.get("in_progress")) is not bool:
        _invalid_snapshot("has an invalid verification state")
    if (
        verification["limit"] < 1 or verification["iterations"] < 1
        or verification["attempted_count"] > verification["limit"]
        or verification["completed_count"] > verification["attempted_count"]
        or verification["remaining_budget"] > verification["limit"]
        or verification["remaining_budget"] != verification["limit"] - verification["attempted_count"]
        or verification["candidate_count"] < verification["attempted_count"]
        or verification["candidate_count"] < verification["completed_count"]
        or verification["unverified_count"] > verification["candidate_count"]
        or verification["omitted_count"] > verification["candidate_count"]
        or verification["unverified_count"] != verification["candidate_count"] - verification["completed_count"]
        or verification["omitted_count"] != verification["candidate_count"] - verification["attempted_count"]
        or verification["failed_count"] + verification["energy_rejected_count"] > verification["attempted_count"]
    ):
        _invalid_snapshot("has inconsistent verification counts")
    response_lane_fields = ("response_lane_reserve", "response_lane_attempted_count")
    if any(field in verification for field in response_lane_fields):
        if any(type(verification.get(field)) is not int or verification[field] < 0 for field in response_lane_fields):
            _invalid_snapshot("has invalid response-lane counts")
        if (
            verification["response_lane_reserve"] > verification["limit"]
            or verification["response_lane_attempted_count"] > verification["attempted_count"]
        ):
            _invalid_snapshot("has inconsistent response-lane counts")
    if snapshot.get("response_status") not in {"ordinary_verified", "no_verified_result"}:
        _invalid_snapshot("has an unsupported response status")
    _validate_snapshot_rows(snapshot)
    return snapshot


def _invalid_snapshot(reason: str) -> None:
    raise GcsimOptimizerGoError("theory_snapshot_invalid", f"Theory snapshot {reason}.")


def _nonnegative_number(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _decimal_counter(value: str) -> int:
    # Native domain sizes are arbitrary-precision decimal strings. Parse small
    # chunks so Python's whole-string conversion limit cannot truncate them.
    result = 0
    for start in range(0, len(value), 9):
        chunk = value[start:start + 9]
        result = result * (10 ** len(chunk)) + int(chunk)
    return result


def _validate_packages(value: Any, wearers: tuple[str, ...] | None = None) -> None:
    if not isinstance(value, list) or len(value) != 4:
        _invalid_snapshot("has an incomplete four-wearer package")
    keys: set[str] = set()
    for package in value:
        if not isinstance(package, dict):
            _invalid_snapshot("has an invalid wearer package")
        wearer = package.get("wearer_key")
        sets = package.get("sets")
        if not isinstance(wearer, str) or not wearer or wearer in keys or not isinstance(sets, list):
            _invalid_snapshot("has an invalid wearer package")
        keys.add(wearer)
        set_keys: set[str] = set()
        for row in sets:
            if not isinstance(row, dict):
                _invalid_snapshot("has an invalid set package")
            uid, count = row.get("set_uid"), row.get("count")
            if not isinstance(uid, str) or not uid or uid in set_keys or type(count) is not int or count not in {2, 4}:
                _invalid_snapshot("has an invalid set package")
            set_keys.add(uid)
        if sum(row["count"] for row in sets) > 4:
            _invalid_snapshot("has an invalid set package")
    if wearers is not None:
        if keys != set(wearers) or tuple(package["wearer_key"] for package in value) != wearers:
            _invalid_snapshot("has mismatched package wearers")


def _validate_allocations(row: dict[str, Any]) -> tuple[str, ...]:
    allocations, witness = row.get("allocations"), row.get("witness45")
    if not isinstance(allocations, list) or len(allocations) != 4 or not isinstance(witness, dict):
        _invalid_snapshot("has an incomplete allocation witness")
    for field in ("Mains", "Lines", "Upgrades"):
        values = witness.get(field)
        if not isinstance(values, list) or len(values) != 4 or any(not isinstance(actor, list) or len(actor) != 5 for actor in values):
            _invalid_snapshot("has an incomplete slot witness")
    wearers: set[str] = set()
    slots = ("flower", "plume", "sands", "goblet", "circlet")
    for actor, allocation in enumerate(allocations):
        if not isinstance(allocation, dict):
            _invalid_snapshot("has an invalid allocation")
        wearer, mains, substats = allocation.get("wearer_key"), allocation.get("main_stats"), allocation.get("substats")
        if not isinstance(wearer, str) or not wearer or wearer in wearers or not isinstance(mains, dict) or not isinstance(substats, list) or len(substats) != 10:
            _invalid_snapshot("has an invalid allocation")
        wearers.add(wearer)
        stat_keys: set[str] = set()
        for stat in substats:
            if not isinstance(stat, dict) or not isinstance(stat.get("stat_key"), str) or not stat["stat_key"] or stat["stat_key"] in stat_keys:
                _invalid_snapshot("has invalid allocation coordinates")
            stat_keys.add(stat["stat_key"])
            if not _nonnegative_number(stat.get("roll_units")) or not _nonnegative_number(stat.get("stat_value")):
                _invalid_snapshot("has invalid allocation numbers")
        spent, unspent = allocation.get("spent_roll_units"), allocation.get("unspent_roll_units")
        if not _nonnegative_number(spent) or not _nonnegative_number(unspent) or abs(spent - 45) > 1e-7 or abs(unspent) > 1e-7:
            _invalid_snapshot("has an incomplete full45 allocation")
        coordinate_units = [0.0] * 10
        for slot, name in enumerate(slots):
            main = witness["Mains"][actor][slot]
            lines, upgrades = witness["Lines"][actor][slot], witness["Upgrades"][actor][slot]
            if not isinstance(main, str) or not main or mains.get(name) != main:
                _invalid_snapshot("has mismatched allocation mains")
            if not isinstance(lines, list) or len(lines) != 4 or any(type(line) is not int or not 0 <= line < 10 for line in lines) or len(set(lines)) != 4:
                _invalid_snapshot("has invalid initial slot lines")
            if any(substats[line]["stat_key"] == main for line in lines):
                _invalid_snapshot("includes a main stat among initial lines")
            if not isinstance(upgrades, list) or len(upgrades) != 4 or any(not _nonnegative_number(value) or value > 5 or abs(value * 4 - round(value * 4)) > 1e-7 for value in upgrades):
                _invalid_snapshot("has invalid quarter-unit upgrades")
            if abs(sum(upgrades) - 5) > 1e-7:
                _invalid_snapshot("has an incomplete full45 slot")
            for line, coordinate in enumerate(lines):
                coordinate_units[coordinate] += 1 + upgrades[line]
        if any(abs(stat["roll_units"] - units) > 1e-7 for stat, units in zip(substats, coordinate_units)):
            _invalid_snapshot("has mismatched allocation roll units")
    return tuple(allocation["wearer_key"] for allocation in allocations)


def _validate_snapshot_rows(snapshot: dict[str, Any]) -> None:
    """Check verified publication structure and search/verification totals."""
    verification = snapshot["verification"]
    families: set[str] = set()
    tuples: set[str] = set()
    frame_wearers: tuple[str, ...] | None = None
    receipt_cohort: tuple[Any, ...] | None = None
    group_tuples = 0
    for section in ("co_leaders", "pending"):
        for row in snapshot[section]:
            if not isinstance(row, dict) or not isinstance(row.get("aliases"), list) or len(row["aliases"]) != 1:
                _invalid_snapshot("has an invalid family row")
            family = row.get("family")
            if not isinstance(family, str) or not family or family in families:
                _invalid_snapshot("has duplicate or missing families")
            families.add(family)
            measurement = theory_measurement(row)
            if (
                not validate_theory_family(row)
                or measurement is None
                or measurement.get("iterations") != verification["iterations"]
                or not _nonnegative_number(row.get("deficit_percent"))
                or type(row.get("refinement_level")) is not int
                or row["refinement_level"] < 0
            ):
                _invalid_snapshot("has invalid family numbers")
            cohort = (
                measurement["frame_sha256"],
                measurement["engine_artifact_sha256"],
                measurement["source_manifest_sha256"],
                measurement["ignore_burst_energy"],
            )
            if receipt_cohort is None:
                receipt_cohort = cohort
            elif cohort != receipt_cohort:
                _invalid_snapshot("mixes ordinary measurement cohorts")
            wearers = _validate_allocations(row)
            if frame_wearers is not None and wearers != frame_wearers:
                _invalid_snapshot("has mismatched family wearers")
            frame_wearers = wearers
            if section == "pending" and (not isinstance(row.get("reason"), str) or not row["reason"]):
                _invalid_snapshot("has an unexplained pending family")
            for alias in row["aliases"]:
                if not isinstance(alias, dict):
                    _invalid_snapshot("has an invalid alias row")
                key = alias.get("tuple_key")
                if (
                    not isinstance(key, str) or not key
                    or not isinstance(alias.get("context_sha256"), str)
                    or re.fullmatch(r"[0-9a-f]{64}", alias["context_sha256"]) is None
                ):
                    _invalid_snapshot("has a missing tuple identity")
                tuples.add(key)
                uncertainty = alias.get("uncertainty")
                if not isinstance(uncertainty, list) or any(not isinstance(value, str) for value in uncertainty):
                    _invalid_snapshot("has invalid alias uncertainty")
                _validate_packages(alias.get("packages"), wearers)
            if section == "co_leaders":
                group_tuples += len(row["aliases"])
    status = snapshot.get("status")
    response_status = snapshot.get("response_status")
    rules = snapshot.get("rules")
    if not isinstance(rules, dict) or rules.get("reference_scope") != "best_attained_comparable_ordinary":
        _invalid_snapshot("has an unsupported reference scope")
    verified_rows = [
        row for section in ("co_leaders", "pending") for row in snapshot[section]
    ]
    completed_count = len(verified_rows)
    if verification["completed_count"] != completed_count:
        _invalid_snapshot("has a mismatched verified-row count")
    if status == "success":
        if response_status != "ordinary_verified" or not verified_rows:
            _invalid_snapshot("claims success without a verified row")
        measured_scores = [theory_measurement(row)["measured_dps"] for row in verified_rows]
        reference = snapshot["reference_score"]
        if not measured_scores or reference != max(measured_scores):
            _invalid_snapshot("has a reference that is not the best attained measurement")
        for row, score in zip(verified_rows, measured_scores):
            expected_deficit = 0.0 if reference == 0 else 100.0 * (reference - score) / reference
            if not math.isclose(row["deficit_percent"], expected_deficit, rel_tol=1e-10, abs_tol=1e-7):
                _invalid_snapshot("has a deficit that does not match measured DPS")
    elif (
        response_status != "no_verified_result"
        or verified_rows
        or snapshot["reference_score"] != 0
        or verification["completed_count"] != 0
    ):
        _invalid_snapshot("has an invalid no-verified result")
    totals = {
        "total_found_families": None, "total_found_tuples": None,
        "found_group_families": len(snapshot["co_leaders"]), "found_group_tuples": group_tuples,
    }
    for field, expected in totals.items():
        if expected is None:
            if type(snapshot.get(field)) is not int or snapshot[field] < 0:
                _invalid_snapshot("has inconsistent search coverage totals")
            continue
        if type(snapshot.get(field)) is not int or snapshot[field] != expected:
            _invalid_snapshot("has inconsistent coverage totals")
    for field, upper in (("sensitivity_group_families", totals["found_group_families"]), ("sensitivity_group_tuples", group_tuples)):
        if type(snapshot.get(field)) is not int or not 0 <= snapshot[field] <= upper:
            _invalid_snapshot("has invalid sensitivity totals")
    for row in snapshot["unavailable"]:
        if not isinstance(row, dict):
            _invalid_snapshot("has an invalid unavailable tuple")
        key, reasons = row.get("tuple_key"), row.get("reasons")
        if not isinstance(key, str) or not key or not isinstance(reasons, list) or not reasons or any(not isinstance(value, str) for value in reasons):
            _invalid_snapshot("has an invalid unavailable tuple")
        tuples.add(key)
        _validate_packages(row.get("packages"), frame_wearers)
    for field in ("domain_tuples", "unseen_tuples"):
        value = snapshot.get(field)
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            _invalid_snapshot("has invalid domain coverage")
    domain, unseen = _decimal_counter(snapshot["domain_tuples"]), _decimal_counter(snapshot["unseen_tuples"])
    if unseen > domain or domain - unseen < len(tuples):
        _invalid_snapshot("has inconsistent domain coverage")
    if snapshot["total_found_tuples"] < len(tuples):
        _invalid_snapshot("has fewer search tuples than the published subset")
    if snapshot["total_found_tuples"] > domain - unseen:
        _invalid_snapshot("has search totals beyond visited set choices")
    if type(snapshot.get("full_cartesian_covered")) is not bool or snapshot["full_cartesian_covered"] != (unseen == 0):
        _invalid_snapshot("has inconsistent full-domain coverage")


def theory_continuation_actions(phase: str, *, verification_in_progress: bool = False) -> tuple[str, ...]:
    if verification_in_progress:
        return ()
    if phase == "first_light":
        return ("breadth", "deep")
    if phase == "breadth_light":
        return ("deep",)
    return ()


class GcsimOptimizerGoTheorySession(_LegacyTheorySession):
    """A single native session with immutable checkpoints and explicit resumes."""

    result_schema_kind = GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND

    def _accept_optimizer_result_status(self, status: Any) -> bool:
        return status in {"success", "no_verified_result"}

    def __init__(
        self,
        request: GcsimOptimizerGoTheoryRequest,
        *,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._consumer_progress_callback = progress_callback
        self._snapshot_lock = threading.Lock()
        self._expected_request_sha256 = ""
        self._session_id = ""
        self._snapshot_version = 0
        self._publication_version = 0
        self._last_snapshot: dict[str, Any] | None = None
        self._command_sequence = 0
        self._pending_command_version: int | None = None
        super().__init__(request, progress_callback=self._consume_progress)

    @property
    def last_snapshot(self) -> dict[str, Any] | None:
        with self._snapshot_lock:
            return deepcopy(self._last_snapshot)

    def run(self) -> dict[str, Any]:
        payload = deepcopy(super().run())
        if payload.get("success") is not True or payload.get("status") != "success" or payload.get("error_code"):
            payload["success"] = False
        if payload.get("success") and self._cancelled.is_set():
            # Cancellation may arrive after the shared reader's final check,
            # during snapshot parsing or run cleanup. Keep the witness only as
            # a retained snapshot, never as terminal success.
            payload = dict(payload)
            payload.pop("result", None)
            payload.update(
                success=False, status="cancelled", error_code="cancelled",
                error="Theory optimization cancelled.",
            )
            if isinstance(payload.get("adapter_timings"), dict):
                payload["adapter_timings"] = {
                    **payload["adapter_timings"], "terminal_status": "cancelled",
                }
        result = payload.get("result")
        if (
            payload.get("success") is True
            and isinstance(result, Mapping)
            and result.get("status") == "no_verified_result"
        ):
            payload.pop("result", None)
            payload.update(
                success=False, status="no_verified_result", error_code="no_verified_result",
                error="No candidate completed ordinary GCSIM verification.",
            )
            payload["retained_snapshot"] = self.last_snapshot or deepcopy(dict(result))
        if not payload.get("success"):
            payload.pop("result", None)
            if payload.get("status") not in {"cancelled", "no_verified_result"}:
                payload["status"] = "failed"
            if isinstance(payload.get("adapter_timings"), dict):
                payload["adapter_timings"]["terminal_status"] = payload["status"]
            snapshot = self.last_snapshot
            if snapshot is not None:
                payload["retained_snapshot"] = snapshot
        return payload

    def _optimizer_command(self, binary: Path, run_dir: Path) -> tuple[str, ...]:
        return (
            *super()._optimizer_command(binary, run_dir),
            "--finish-file", str(run_dir / "finish-requested"),
            "--theory-control-file", str(run_dir / "theory-control.json"),
        )

    def _require_search_not_finished_before_result(self) -> None:
        if self._finish_requested.is_set() and self.last_snapshot is None:
            raise GcsimOptimizerGoError("finish_no_result", "Theory stopped before a complete legal target was found.")

    def _run_go_optimizer(self, *, prepared, compact, run_dir, started):
        with self._snapshot_lock:
            self._expected_request_sha256 = prepared["request_sha256"]
        result = super()._run_go_optimizer(
            prepared=prepared, compact=compact, run_dir=run_dir, started=started,
        )
        return self._store_snapshot(result)

    def _store_snapshot(self, value: Mapping[str, Any]) -> dict[str, Any]:
        with self._snapshot_lock:
            previous = self._last_snapshot
            snapshot = copy_theory_snapshot(
                value,
                expected_request_sha256=self._expected_request_sha256,
                expected_session_id=self._session_id,
                newer_than=self._publication_version,
                previous_snapshot=previous,
            )
            search_version = snapshot["snapshot_version"]
            if search_version < self._snapshot_version:
                raise GcsimOptimizerGoError("theory_snapshot_stale", "Theory search snapshot moved backwards.")
            if previous is not None:
                if _THEORY_PHASE_ORDER[snapshot["phase"]] < _THEORY_PHASE_ORDER[previous["phase"]]:
                    raise GcsimOptimizerGoError("theory_snapshot_stale", "Theory search phase moved backwards.")
                before, after = previous["verification"], snapshot["verification"]
                if before["limit"] != after["limit"] or before["iterations"] != after["iterations"]:
                    _invalid_snapshot("changed the lifetime verification budget")
                for field in (
                    "attempted_count", "completed_count", "failed_count",
                    "energy_rejected_count", "candidate_count", "omitted_count",
                ):
                    if after[field] < before[field]:
                        _invalid_snapshot("decreased a cumulative verification counter")
                if after["remaining_budget"] > before["remaining_budget"]:
                    _invalid_snapshot("increased the remaining verification budget")
                if snapshot["total_found_families"] < previous["total_found_families"] or snapshot["total_found_tuples"] < previous["total_found_tuples"]:
                    _invalid_snapshot("decreased cumulative search totals")
            self._session_id = snapshot["session_id"]
            if search_version > self._snapshot_version or (
                previous is not None and snapshot["phase"] != previous["phase"]
            ):
                self._snapshot_version = search_version
                self._pending_command_version = None
            self._publication_version = snapshot["publication_version"]
            self._last_snapshot = snapshot
            return deepcopy(snapshot)

    def _consume_progress(self, event: dict[str, Any]) -> None:
        forwarded = deepcopy(event)
        if "theory_snapshot" in event:
            # The shared reader supplies only progress records. A nested result
            # still has to match the prepared request, the envelope and session.
            if (
                not self._expected_request_sha256
                or event.get("request_sha256") != self._expected_request_sha256
            ):
                return
            try:
                forwarded["theory_snapshot"] = self._store_snapshot(event["theory_snapshot"])
            except GcsimOptimizerGoError:
                return  # Invalid/stale progress must never replace a legal snapshot.
        if self._consumer_progress_callback is not None:
            self._consumer_progress_callback(forwarded)

    def request_continuation(self, action: str, *, snapshot_version: int) -> bool:
        """Publish one version-bound command; no automatic phase chaining."""
        if action not in {"breadth", "deep"} or type(snapshot_version) is not int:
            return False
        # Follow the lifecycle's lock order; its finally block clears run_dir
        # under the same lock before releasing the run directory lease.
        with self._finish_lock, self._snapshot_lock:
            snapshot = self._last_snapshot
            if (
                self._cancelled.is_set() or self._finish_requested.is_set()
                or self._run_dir is None or snapshot is None
                or snapshot["verification"]["in_progress"]
                or snapshot_version != self._snapshot_version
                or self._pending_command_version == snapshot_version
                or action not in theory_continuation_actions(snapshot["phase"])
            ):
                return False
            sequence = self._command_sequence + 1
            command = {
                "schema_kind": THEORY_SESSION_COMMAND_KIND,
                "session_id": self._session_id,
                "request_sha256": self._expected_request_sha256,
                "snapshot_version": snapshot_version,
                "sequence": sequence,
                "action": action,
            }
            temporary = self._run_dir / f".theory-control-{uuid4().hex}.tmp"
            try:
                temporary.write_text(json.dumps(command, allow_nan=False) + "\n", encoding="utf-8")
                os.replace(temporary, self._run_dir / "theory-control.json")
            except OSError:
                return False
            finally:
                temporary.unlink(missing_ok=True)
            self._command_sequence = sequence
            self._pending_command_version = snapshot_version
            return True


def format_gcsim_optimizer_go_theory_session_result(payload: Mapping[str, Any], *, include_rows: bool = True) -> str:
    """Format a compact UI summary or a lossless diagnostic text projection."""
    from localization import tr

    lines: list[str] = []
    if payload.get("success") is not True or payload.get("error_code"):
        error_code = str(payload.get("error_code") or "")
        title_key = (
            "gcsim.optimizer.finish_no_result_title" if error_code == "finish_no_result"
            else "gcsim.optimizer.theory_session.no_verified_result" if payload.get("status") == "no_verified_result"
            else "gcsim.optimizer.theory_cancelled" if payload.get("status") == "cancelled"
            else "gcsim.optimizer.theory_failed"
        )
        lines.append(tr(title_key))
        error_keys = {
            "finish_no_result": "gcsim.optimizer.theory_session.no_result",
            "no_verified_result": "gcsim.optimizer.theory_session.no_verified_result_detail",
            "theory_profile_incomplete": "gcsim.optimizer.theory_profile_required",
            "theory_finite_energy_unsupported": "gcsim.optimizer.theory_finite_energy_unsupported",
            "rotation_unbounded_dummy_target": "gcsim.optimizer.rotation_unbounded_dummy_target",
            "theory_snapshot_invalid": "gcsim.optimizer.theory_session.snapshot_invalid",
            "theory_snapshot_identity_mismatch": "gcsim.optimizer.theory_session.snapshot_invalid",
            "theory_snapshot_stale": "gcsim.optimizer.theory_session.snapshot_invalid",
        }
        if error_code != "no_verified_result":
            reason = tr(error_keys[error_code]) if error_code in error_keys else str(payload.get("error") or "-")
            lines.append(tr("gcsim.optimizer.reason").format(reason=reason))
        else:
            lines.append(tr("gcsim.optimizer.theory_session.no_verified_result_detail"))
        result = payload.get("retained_snapshot")
        if not isinstance(result, Mapping):
            return "\n".join(lines)
        if result.get("status") != "no_verified_result":
            lines.extend(("", tr("gcsim.optimizer.theory_session.retained")))
        elif error_code != "no_verified_result":
            lines.append(tr("gcsim.optimizer.theory_session.no_verified_result_detail"))
    else:
        result = payload.get("result")
        if not isinstance(result, Mapping):
            return tr("gcsim.optimizer.theory_failed")
        if result.get("status") == "no_verified_result":
            verification = result.get("verification")
            key = (
                "gcsim.optimizer.theory_session.checking"
                if isinstance(verification, Mapping) and verification.get("in_progress") is True
                else "gcsim.optimizer.theory_session.no_verified_result"
            )
            lines.extend((tr(key), tr("gcsim.optimizer.theory_session.no_verified_result_detail")))
        else:
            lines.append(tr("gcsim.optimizer.theory_session.title"))
    phase = str(result.get("phase") or "")
    has_verified_rows = (
        result.get("status") == "success"
        and result.get("response_status") == "ordinary_verified"
    )
    if not has_verified_rows:
        reference_key = "gcsim.optimizer.theory_display.reference_unavailable"
    elif result.get("reference_score") == 0:
        reference_key = "gcsim.optimizer.theory_display.reference_zero"
    else:
        reference_key = "gcsim.optimizer.theory_session.reference" if include_rows else (
            "gcsim.optimizer.theory_display.reference"
        )
    lines.extend((
        tr("gcsim.optimizer.theory_session.phase." + phase),
        tr("gcsim.optimizer.theory_session.guidance" if include_rows else "gcsim.optimizer.theory_display.guidance"),
        tr(reference_key).format(
            dps=_number(result.get("reference_score")),
            band=_number(result.get("practical_band_percent")),
            sensitivity=_number(result.get("sensitivity_band_percent")),
        ),
        tr("gcsim.optimizer.theory_session.coverage" if include_rows else "gcsim.optimizer.theory_display.coverage").format(
            families=result.get("found_group_families", len(result.get("co_leaders") or ())),
            tuples=result.get("found_group_tuples", "-"),
            found_families=result.get("total_found_families", "-"),
            found_tuples=result.get("total_found_tuples", "-"),
        ),
        tr("gcsim.optimizer.theory_session.sensitivity").format(
            families=result.get("sensitivity_group_families", "-"),
            tuples=result.get("sensitivity_group_tuples", "-"),
        ),
        tr("gcsim.optimizer.theory_session.domain_coverage").format(
            domain=result.get("domain_tuples", "-"), unseen=result.get("unseen_tuples", "-"),
        ),
        tr("gcsim.optimizer.theory_session.coverage_complete")
        if result.get("full_cartesian_covered") is True
        else tr("gcsim.optimizer.theory_session.coverage_partial"),
    ))
    verification = result.get("verification")
    if isinstance(verification, Mapping):
        verification_line = tr("gcsim.optimizer.theory_display.verification").format(
            iterations=verification.get("iterations", 0),
            attempted=verification.get("attempted_count", 0),
            limit=verification.get("limit", 0),
            verified=verification.get("completed_count", 0),
            candidates=verification.get("candidate_count", 0),
            unverified=verification.get("unverified_count", 0),
            failed=verification.get("failed_count", 0),
            energy_rejected=verification.get("energy_rejected_count", 0),
            omitted=verification.get("omitted_count", 0),
            remaining=verification.get("remaining_budget", 0),
        )
        if "response_lane_reserve" in verification and "response_lane_attempted_count" in verification:
            verification_line += " " + tr("gcsim.optimizer.theory_display.response_lane").format(
                attempted=verification["response_lane_attempted_count"],
                reserve=verification["response_lane_reserve"],
            )
        lines.append(verification_line)
    if result.get("source_upper") == "unbounded" or result.get("outer_upper") == "unbounded":
        lines.append(tr("gcsim.optimizer.theory_session.unbounded"))
    if result.get("finished_early"):
        lines.append(tr("gcsim.optimizer.search_finished_by_user"))
    if include_rows:
        lines.extend(_format_family_rows(result.get("co_leaders")))
    pending = result.get("pending")
    if include_rows and isinstance(pending, list) and pending:
        lines.extend(("", tr("gcsim.optimizer.theory_session.pending")))
        lines.extend(_format_family_rows(pending))
    unavailable = result.get("unavailable")
    if not include_rows and isinstance(unavailable, list) and unavailable:
        lines.append(tr("gcsim.optimizer.theory_display.unavailable_count").format(count=len(unavailable)))
    if include_rows and isinstance(unavailable, list) and unavailable:
        lines.extend(("", tr("gcsim.optimizer.theory_session.unavailable")))
        for row in unavailable:
            if not isinstance(row, Mapping):
                continue
            lines.append(tr("gcsim.optimizer.theory_session.choice").format(key=row.get("tuple_key") or "-"))
            lines.extend(_format_packages(row.get("packages")))
            lines.append(tr("gcsim.optimizer.theory_session.limitations").format(
                reasons=", ".join(format_optimizer_warning(value) for value in row.get("reasons") or ()),
            ))
    warnings = tuple(result.get("warnings") or ()) + tuple(payload.get("adapter_warnings") or ())
    if warnings:
        if include_rows:
            lines.extend(("", tr("gcsim.optimizer.theory_session.limitations").format(
                reasons=", ".join(format_optimizer_warning(value) for value in warnings),
            )))
        else:
            lines.append(tr("gcsim.optimizer.theory_display.limit_count").format(count=len(warnings)))
    return "\n".join(lines)


def _format_family_rows(value: Any) -> list[str]:
    from localization import tr

    lines: list[str] = []
    for ordinal, row in enumerate(value if isinstance(value, list) else (), start=1):
        if not isinstance(row, Mapping):
            continue
        lines.extend(("", tr("gcsim.optimizer.theory_session.family").format(
            family=ordinal,
            dps=_number(theory_measurement(row).get("measured_dps") if theory_measurement(row) else None),
            deficit=_number(row.get("deficit_percent")),
        )))
        for allocation in row.get("allocations") or ():
            if not isinstance(allocation, Mapping):
                continue
            mains = allocation.get("main_stats") or {}
            mains_text = "/".join(str(mains.get(slot) or "-") for slot in ("sands", "goblet", "circlet"))
            substats = ", ".join(
                tr("gcsim.optimizer.theory_session.rolls").format(stat=stat.get("stat_key") or "-", rolls=_number(stat.get("roll_units")))
                for stat in allocation.get("substats") or () if isinstance(stat, Mapping)
            )
            lines.append(tr("gcsim.optimizer.theory_session.allocation").format(
                wearer=allocation.get("wearer_key") or "-", mains=mains_text, substats=substats or "-",
            ))
        if row.get("reason"):
            lines.append(tr("gcsim.optimizer.reason").format(reason=_format_family_reason(row["reason"])))
        for alias in row.get("aliases") or ():
            if not isinstance(alias, Mapping):
                continue
            lines.append(tr("gcsim.optimizer.theory_session.choice").format(key=alias.get("tuple_key") or "-"))
            lines.extend(_format_packages(alias.get("packages")))
            if alias.get("uncertainty"):
                lines.append(tr("gcsim.optimizer.theory_session.limitations").format(
                    reasons=", ".join(format_optimizer_warning(value) for value in alias["uncertainty"]),
                ))
    return lines


def _format_family_reason(value: Any) -> str:
    from localization import tr

    keys = {
        "below_practical_band": "gcsim.optimizer.theory_session.below_band",
        "below_verified_practical_band": "gcsim.optimizer.theory_session.below_band",
        "below_practical_band_not_deeply_refined": "gcsim.optimizer.theory_session.below_band_unrefined",
    }
    code = str(value.get("code") or "") if isinstance(value, Mapping) else str(value)
    return tr(keys[code]) if code in keys else format_optimizer_warning(value)


def _format_packages(value: Any) -> list[str]:
    from localization import tr

    lines: list[str] = []
    for package in value if isinstance(value, list) else ():
        if not isinstance(package, Mapping):
            continue
        sets = " + ".join(
            tr("gcsim.optimizer.theory_session.set").format(uid=row.get("set_uid") or "-", count=row.get("count", "-"))
            for row in package.get("sets") or () if isinstance(row, Mapping)
        ) or tr("gcsim.optimizer.theory_session.no_bonus")
        lines.append(f"  {package.get('wearer_key') or '-'}: {sets}")
    return lines


def _number(value: Any) -> str:
    if type(value) in (int, float) and math.isfinite(value):
        return f"{value:,.6g}"
    return "-"


__all__ = [
    "GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND",
    "GcsimOptimizerGoTheorySession",
    "copy_theory_snapshot",
    "format_gcsim_optimizer_go_theory_session_result",
    "theory_continuation_actions",
]
